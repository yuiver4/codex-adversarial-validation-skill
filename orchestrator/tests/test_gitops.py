from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from orchestrator.gitops import CandidateBuilder, GitRepository, MeasurementExecutor
from orchestrator.model import OrchestratorError, RoleInvocation, TaskContract
from orchestrator.tests.helpers import git, init_repo


def _windows_process_is_running(pid: int) -> bool:
    import ctypes
    from ctypes import wintypes

    process_query_limited_information = 0x1000
    still_active = 259
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
    if not handle:
        return False
    try:
        exit_code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return False
        return exit_code.value == still_active
    finally:
        kernel32.CloseHandle(handle)


def author_invocation() -> RoleInvocation:
    return RoleInvocation(
        role="AUTHOR_IMPLEMENT",
        thread_id="author-thread",
        turn_id="author-turn",
        report={"summary": "candidate", "action_summary": ["edited files"]},
        observable_events=({"method": "turn/completed", "status": "completed"},),
    )


class RecordingTerminator:
    def __init__(self, success: bool = True) -> None:
        self.called = 0
        self.success = success

    def spawn(self, argv, **arguments):
        if os.name == "nt":
            arguments["creationflags"] = getattr(
                subprocess, "CREATE_NEW_PROCESS_GROUP", 0
            )
        else:
            arguments["start_new_session"] = True
        return subprocess.Popen(list(argv), **arguments)

    def terminate(self, process: subprocess.Popen[bytes]) -> bool:
        self.called += 1
        process.kill()
        process.wait(timeout=3)
        return self.success


class CleanupFailureRepository(GitRepository):
    def new_worktree(self, base_commit: str, prefix: str):
        inner = super().new_worktree(base_commit, prefix)

        class Lease:
            path = inner.path

            @staticmethod
            def cleanup() -> None:
                inner.cleanup()
                raise OrchestratorError("WORKTREE_CLEANUP_FAILED", "injected")

        return Lease()


class GitCandidateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="trace-git-test-")
        self.root = Path(self.temporary.name) / "repo"
        self.base = init_repo(self.root)
        self.repository = GitRepository(self.root)
        self.contract = TaskContract.create("implement the requested change", ["keep it small"])

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _simple_candidate(self):
        lease = self.repository.new_worktree(self.base, "trace-author-test-")
        try:
            (lease.path / "result.txt").write_text("candidate\n", encoding="utf-8")
            return CandidateBuilder(self.repository).freeze(
                lease.path, self.base, self.contract, author_invocation()
            )
        finally:
            lease.cleanup()

    def test_dubious_ownership_is_structured_without_automatic_trust(self) -> None:
        sensitive = "C:/Users/private-owner/secret-repository"
        stderr = (
            "fatal: detected dubious ownership in repository at '"
            f"{sensitive}'\nTo add an exception for this directory, call:\n\n"
            f"git config --global --add safe.directory {sensitive}\n"
        ).encode("utf-8")
        completed = subprocess.CompletedProcess(
            ["git", "status"], 128, stdout=b"", stderr=stderr
        )

        with mock.patch("orchestrator.gitops.subprocess.run", return_value=completed) as run:
            with self.assertRaises(OrchestratorError) as caught:
                self.repository.run("status")

        error = caught.exception
        self.assertEqual(error.code, "GIT_DUBIOUS_OWNERSHIP")
        self.assertEqual(error.detail, "")
        self.assertEqual(run.call_args.args[0], ["git", "status"])
        self.assertNotIn("safe.directory", run.call_args.args[0])

    def test_partial_or_unrelated_git_failures_remain_generic(self) -> None:
        failures = (
            b"fatal: not a git repository: C:/private/path",
            b"fatal: safe.directory is not valid here",
            b"fatal: detected dubious ownership in repository metadata",
        )
        for stderr in failures:
            with self.subTest(stderr=stderr):
                completed = subprocess.CompletedProcess(
                    ["git", "status"], 128, stdout=b"", stderr=stderr
                )
                with mock.patch(
                    "orchestrator.gitops.subprocess.run", return_value=completed
                ):
                    with self.assertRaises(OrchestratorError) as caught:
                        self.repository.run("status")

                self.assertEqual(caught.exception.code, "GIT_COMMAND_FAILED")
                self.assertIn(stderr.decode("utf-8"), caught.exception.detail)

    def test_temporary_index_includes_all_git_change_classes_without_touching_author_index(self) -> None:
        for name, value in {
            "staged.txt": "old staged\n",
            "delete.txt": "delete me\n",
            "rename-old.txt": "rename payload\n",
        }.items():
            (self.root / name).write_text(value, encoding="utf-8")
        git(self.root, "add", ".")
        git(self.root, "commit", "--amend", "--no-edit")
        self.base = git(self.root, "rev-parse", "HEAD").decode("ascii").strip()

        lease = self.repository.new_worktree(self.base, "trace-author-all-")
        try:
            (lease.path / "staged.txt").write_text("new staged\n", encoding="utf-8")
            git(lease.path, "add", "staged.txt")
            (lease.path / "base.txt").write_text("unstaged\n", encoding="utf-8")
            (lease.path / "delete.txt").unlink()
            (lease.path / "rename-old.txt").rename(lease.path / "rename-new.txt")
            (lease.path / "untracked.txt").write_text("untracked\n", encoding="utf-8")
            binary = b"\x00\xff\x10binary\x00payload"
            (lease.path / "untracked.bin").write_bytes(binary)
            index_location = Path(
                git(lease.path, "rev-parse", "--git-path", "index")
                .decode("utf-8")
                .strip()
            )
            if not index_location.is_absolute():
                index_location = lease.path / index_location
            index_before = index_location.read_bytes()

            candidate = CandidateBuilder(self.repository).freeze(
                lease.path, self.base, self.contract, author_invocation()
            )

            self.assertEqual(index_location.read_bytes(), index_before)
            self.assertIn(b"untracked.txt", candidate.patch)
            self.assertIn(b"GIT binary patch", candidate.patch)
            self.assertIn(b"deleted file mode", candidate.patch)
            self.assertIn(b"rename from rename-old.txt", candidate.patch)
            self.assertIn(b"rename to rename-new.txt", candidate.patch)
            candidate.verify_binding(self.contract)

            verify = self.repository.new_worktree(self.base, "trace-inspect-")
            try:
                self.repository.apply_patch_to_index(verify.path, candidate.patch)
                self.assertEqual((verify.path / "untracked.bin").read_bytes(), binary)
                self.assertEqual(
                    self.repository.worktree_tree_id(verify.path), candidate.tree_id
                )
            finally:
                verify.cleanup()
        finally:
            lease.cleanup()

    def test_measurement_writes_are_disposable_and_do_not_change_frozen_hash(self) -> None:
        candidate = self._simple_candidate()
        before = candidate.patch_sha256
        report = MeasurementExecutor().run(
            self.repository,
            candidate,
            self.contract,
            [
                sys.executable,
                "-c",
                "from pathlib import Path; Path('measurement-only.txt').write_text('x')",
            ],
            5,
        )
        self.assertEqual(report.status, "COMPLETED")
        self.assertEqual(report.exit_code, 0)
        self.assertEqual(report.frozen_patch_sha256_before, before)
        self.assertEqual(report.frozen_patch_sha256_after, before)
        self.assertNotIn(b"measurement-only.txt", candidate.patch)
        self.assertFalse((self.root / "measurement-only.txt").exists())

    def test_timeout_calls_process_tree_terminator_and_blocks(self) -> None:
        candidate = self._simple_candidate()
        terminator = RecordingTerminator()
        report = MeasurementExecutor(terminator).run(
            self.repository,
            candidate,
            self.contract,
            [sys.executable, "-c", "import time; time.sleep(10)"],
            0.1,
        )
        self.assertEqual(terminator.called, 1)
        self.assertEqual(report.status, "BLOCKED")
        self.assertEqual(report.code, "MEASUREMENT_TIMEOUT", report.to_dict())
        self.assertTrue(report.process_tree_terminated)
        self.assertTrue(report.cleanup_succeeded)

    @unittest.skipUnless(
        os.name == "nt" and os.environ.get("TRACE_RUN_WINDOWS_PROCESS_TREE_TEST") == "1",
        "set TRACE_RUN_WINDOWS_PROCESS_TREE_TEST=1 for the Windows process-tree probe",
    )
    def test_windows_timeout_kills_real_grandchild_process(self) -> None:
        candidate = self._simple_candidate()
        script = (
            "import os,subprocess,sys,time; "
            "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); "
            "print(f'{os.getpid()} {child.pid}',flush=True); time.sleep(30)"
        )
        report = MeasurementExecutor().run(
            self.repository,
            candidate,
            self.contract,
            [sys.executable, "-c", script],
            0.5,
        )
        self.assertEqual(report.status, "BLOCKED")
        self.assertEqual(report.code, "MEASUREMENT_TIMEOUT", report.to_dict())
        self.assertTrue(report.process_tree_terminated)
        pids = [int(value) for value in report.stdout.strip().split()]
        self.assertEqual(len(pids), 2, report.stdout)
        self.assertFalse(_windows_process_is_running(pids[0]))
        self.assertFalse(_windows_process_is_running(pids[1]))

    @unittest.skipUnless(os.name == "nt", "Windows Job Object probe")
    def test_windows_successful_parent_cannot_leave_detached_child(self) -> None:
        candidate = self._simple_candidate()
        detached_flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
        script = (
            "import subprocess,sys; "
            f"flags={detached_flags}; "
            "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'],"
            "stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,"
            "creationflags=flags); print(child.pid,flush=True)"
        )
        report = MeasurementExecutor().run(
            self.repository,
            candidate,
            self.contract,
            [sys.executable, "-c", script],
            5,
        )
        self.assertEqual(report.status, "COMPLETED", report.to_dict())
        self.assertEqual(report.exit_code, 0)
        self.assertTrue(report.process_tree_terminated)
        child_pid = int(report.stdout.strip())
        self.assertFalse(_windows_process_is_running(child_pid))

    def test_termination_or_worktree_cleanup_failure_is_blocked(self) -> None:
        candidate = self._simple_candidate()
        failed_terminator = RecordingTerminator(success=False)
        termination = MeasurementExecutor(failed_terminator).run(
            self.repository,
            candidate,
            self.contract,
            [sys.executable, "-c", "import time; time.sleep(10)"],
            0.1,
        )
        self.assertEqual(termination.code, "PROCESS_TREE_TERMINATION_FAILED")
        self.assertEqual(termination.status, "BLOCKED")

        cleanup_repository = CleanupFailureRepository(self.root)
        cleanup = MeasurementExecutor().run(
            cleanup_repository,
            candidate,
            self.contract,
            [sys.executable, "-c", "print('ok')"],
            5,
        )
        self.assertEqual(cleanup.code, "WORKTREE_CLEANUP_FAILED")
        self.assertEqual(cleanup.status, "BLOCKED")
        self.assertFalse(cleanup.cleanup_succeeded)


if __name__ == "__main__":
    unittest.main()
