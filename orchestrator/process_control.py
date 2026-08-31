from __future__ import annotations

import errno
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


@dataclass(frozen=True)
class _Containment:
    kind: str
    identifier: int
    temporary_root: Path | None = None


if os.name == "nt":
    import ctypes
    from ctypes import wintypes

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    _kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    _kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    _kernel32.SetInformationJobObject.restype = wintypes.BOOL
    _kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    _kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    _kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    _kernel32.TerminateJobObject.restype = wintypes.BOOL
    _kernel32.QueryInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    _kernel32.QueryInformationJobObject.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL

    class _BasicLimitInformation(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _IoCounters(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class _ExtendedLimitInformation(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _BasicLimitInformation),
            ("IoInfo", _IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    class _BasicAccountingInformation(ctypes.Structure):
        _fields_ = [
            ("TotalUserTime", ctypes.c_longlong),
            ("TotalKernelTime", ctypes.c_longlong),
            ("ThisPeriodTotalUserTime", ctypes.c_longlong),
            ("ThisPeriodTotalKernelTime", ctypes.c_longlong),
            ("TotalPageFaultCount", wintypes.DWORD),
            ("TotalProcesses", wintypes.DWORD),
            ("ActiveProcesses", wintypes.DWORD),
            ("TotalTerminatedProcesses", wintypes.DWORD),
        ]

    _JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION = 1
    _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
    _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000


def _create_windows_job() -> int:
    handle = _kernel32.CreateJobObjectW(None, None)
    if not handle:
        raise OSError(ctypes.get_last_error(), "CreateJobObjectW failed")
    information = _ExtendedLimitInformation()
    information.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not _kernel32.SetInformationJobObject(
        handle,
        _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
        ctypes.byref(information),
        ctypes.sizeof(information),
    ):
        error = ctypes.get_last_error()
        _kernel32.CloseHandle(handle)
        raise OSError(error, "SetInformationJobObject failed")
    return int(handle)


def _windows_active_processes(handle: int) -> int:
    information = _BasicAccountingInformation()
    returned = wintypes.DWORD()
    if not _kernel32.QueryInformationJobObject(
        wintypes.HANDLE(handle),
        _JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION,
        ctypes.byref(information),
        ctypes.sizeof(information),
        ctypes.byref(returned),
    ):
        raise OSError(ctypes.get_last_error(), "QueryInformationJobObject failed")
    return int(information.ActiveProcesses)


class ProcessTreeTerminator:
    """Spawn in an owned OS container and verify it is empty before release."""

    def __init__(self) -> None:
        self._containments: dict[int, _Containment] = {}
        self._lock = threading.Lock()

    def spawn(
        self,
        argv: Sequence[str],
        **popen_arguments: Any,
    ) -> subprocess.Popen[Any]:
        command = list(argv)
        if not command or any(not isinstance(item, str) or not item for item in command):
            raise ValueError("command must contain non-empty strings")
        if os.name != "nt":
            popen_arguments["start_new_session"] = True
            process = subprocess.Popen(command, **popen_arguments)
            with self._lock:
                self._containments[process.pid] = _Containment("process-group", process.pid)
            return process

        job_handle = _create_windows_job()
        temporary_root = Path(tempfile.mkdtemp(prefix="trace-adv-process-"))
        gate = temporary_root / "assigned-to-job"
        wrapper = Path(__file__).with_name("process_wrapper.py")
        wrapped_command = [
            sys.executable,
            "-B",
            "-X",
            "utf8",
            str(wrapper),
            "--gate",
            str(gate),
            "--",
            *command,
        ]
        popen_arguments["creationflags"] = (
            int(popen_arguments.get("creationflags", 0))
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        )
        process: subprocess.Popen[Any] | None = None
        try:
            process = subprocess.Popen(wrapped_command, **popen_arguments)
            process_handle = getattr(process, "_handle", None)
            if process_handle is None or not _kernel32.AssignProcessToJobObject(
                wintypes.HANDLE(job_handle), wintypes.HANDLE(int(process_handle))
            ):
                raise OSError(ctypes.get_last_error(), "AssignProcessToJobObject failed")
            with self._lock:
                self._containments[process.pid] = _Containment(
                    "windows-job", job_handle, temporary_root
                )
            gate.write_text("go", encoding="ascii")
            return process
        except BaseException:
            if process is not None:
                with self._lock:
                    self._containments.pop(process.pid, None)
            if process is not None and process.poll() is None:
                process.kill()
                process.wait(timeout=3)
            _kernel32.CloseHandle(wintypes.HANDLE(job_handle))
            shutil.rmtree(temporary_root, ignore_errors=True)
            raise

    def terminate(self, process: subprocess.Popen[Any]) -> bool:
        with self._lock:
            containment = self._containments.pop(process.pid, None)
        if containment is None:
            return False
        if containment.kind == "windows-job":
            return self._terminate_windows(process, containment)
        return self._terminate_process_group(process, containment.identifier)

    @staticmethod
    def _terminate_windows(
        process: subprocess.Popen[Any], containment: _Containment
    ) -> bool:
        handle = containment.identifier
        success = True
        try:
            if _windows_active_processes(handle) > 0 and not _kernel32.TerminateJobObject(
                wintypes.HANDLE(handle), 1
            ):
                success = False
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                success = False
            deadline = time.monotonic() + 5.0
            while _windows_active_processes(handle) > 0 and time.monotonic() < deadline:
                time.sleep(0.02)
            if _windows_active_processes(handle) != 0:
                success = False
        except (OSError, subprocess.SubprocessError):
            success = False
        finally:
            if not _kernel32.CloseHandle(wintypes.HANDLE(handle)):
                success = False
            if containment.temporary_root is not None:
                try:
                    shutil.rmtree(containment.temporary_root)
                except OSError:
                    success = False
        return success and process.poll() is not None

    @staticmethod
    def _terminate_process_group(
        process: subprocess.Popen[Any], process_group: int
    ) -> bool:
        success = True
        try:
            os.killpg(process_group, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except OSError:
            success = False
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process_group, signal.SIGKILL)
                process.wait(timeout=3)
            except (OSError, subprocess.SubprocessError):
                success = False
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            try:
                os.killpg(process_group, 0)
            except ProcessLookupError:
                return success and process.poll() is not None
            except OSError as error:
                if error.errno == errno.ESRCH:
                    return success and process.poll() is not None
                success = False
                break
            time.sleep(0.02)
        return False
