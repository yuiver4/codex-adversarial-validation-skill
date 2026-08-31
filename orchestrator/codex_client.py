from __future__ import annotations

import json
import math
import os
import queue
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .model import OrchestratorError, RoleInvocation, canonical_json_bytes
from .process_control import ProcessTreeTerminator


READ_ONLY = "read-only"
WORKSPACE_WRITE = "workspace-write"
EFFORT_VALUES = {"none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"}

VALIDATION_EXECUTION_ROLES = frozenset(
    {
        "PLAN_TRACE",
        "PLAN_AV",
        "PLAN_JUDGE",
        "PLAN_TARGETED_RECHECK",
        "RESULT_TRACE",
        "RESULT_AV",
        "RESULT_JUDGE",
        "RESULT_TARGETED_RECHECK",
    }
)


# These notifications add no evidence needed by the parent gate. Asking the
# server not to emit them keeps the client focused on item boundaries and the
# terminal turn result without retaining reasoning or streaming text deltas.
QUIET_NOTIFICATION_METHODS = (
    "account/rateLimits/updated",
    "item/agentMessage/delta",
    "item/commandExecution/outputDelta",
    "item/commandExecution/terminalInteraction",
    "item/fileChange/outputDelta",
    "item/fileChange/patchUpdated",
    "item/mcpToolCall/progress",
    "item/plan/delta",
    "item/reasoning/summaryPartAdded",
    "item/reasoning/summaryTextDelta",
    "item/reasoning/textDelta",
    "mcpServer/startupStatus/updated",
    "remoteControl/status/changed",
    "thread/started",
    "thread/status/changed",
    "thread/tokenUsage/updated",
    "turn/diff/updated",
    "turn/plan/updated",
    "turn/started",
)

SANITIZED_INFORMATIONAL_METHODS = {
    "configWarning",
    "deprecationNotice",
    "model/verification",
    "warning",
    "windows/worldWritableWarning",
    "windowsSandbox/setupCompleted",
}


@dataclass(frozen=True)
class RoleRequest:
    role: str
    payload: Mapping[str, Any]
    output_schema: Mapping[str, Any]
    cwd: Path
    sandbox: str
    base_instructions: str
    isolate_project_instructions: bool = False


@dataclass(frozen=True)
class RoleExecutionProfile:
    """Requested App Server execution controls for one role."""

    model: str | None = None
    effort: str | None = None
    timeout_seconds: float | None = None

    def __post_init__(self) -> None:
        if self.model is not None and (not isinstance(self.model, str) or not self.model):
            raise ValueError("model must be a non-empty string")
        if self.effort is not None and self.effort not in EFFORT_VALUES:
            raise ValueError("unsupported effort")
        if self.timeout_seconds is not None and (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, (int, float))
            or not math.isfinite(self.timeout_seconds)
            or self.timeout_seconds <= 0
        ):
            raise ValueError("timeout_seconds must be positive")

    def overlay(self, override: "RoleExecutionProfile | None") -> "RoleExecutionProfile":
        if override is None:
            return self
        return RoleExecutionProfile(
            model=override.model if override.model is not None else self.model,
            effort=override.effort if override.effort is not None else self.effort,
            timeout_seconds=(
                override.timeout_seconds
                if override.timeout_seconds is not None
                else self.timeout_seconds
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "effort": self.effort,
            "timeout_seconds": self.timeout_seconds,
        }


def resolve_execution_profile(
    role: str,
    role_execution: Mapping[str, RoleExecutionProfile],
    fallback_timeout_seconds: float,
) -> RoleExecutionProfile:
    """Resolve explicit job profiles without choosing a hidden model or effort."""

    resolved = RoleExecutionProfile().overlay(role_execution.get("default"))
    if role in VALIDATION_EXECUTION_ROLES:
        resolved = resolved.overlay(role_execution.get("validation"))
    resolved = resolved.overlay(role_execution.get(role))
    if resolved.timeout_seconds is None:
        resolved = RoleExecutionProfile(
            model=resolved.model,
            effort=resolved.effort,
            timeout_seconds=fallback_timeout_seconds,
        )
    return resolved


def _default_command() -> list[str]:
    executable = shutil.which("codex")
    if executable is None:
        raise OrchestratorError("CODEX_NOT_FOUND")
    return [executable, "--disable", "hooks", "app-server", "--stdio"]


def _child_environment() -> dict[str, str]:
    allowed = {
        "APPDATA",
        "CODEX_HOME",
        "COMSPEC",
        "HOMEDRIVE",
        "HOMEPATH",
        "LANG",
        "LC_ALL",
        "LOCALAPPDATA",
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "WINDIR",
    }
    environment = {
        key: value for key, value in os.environ.items() if key.upper() in allowed
    }
    environment["PYTHONUTF8"] = "1"
    return environment


def _read_lines(stream: Any, output: queue.Queue[str | None]) -> None:
    try:
        for line in stream:
            output.put(line)
    finally:
        output.put(None)


def _drain_stderr(stream: Any, lines: list[str]) -> None:
    for line in stream:
        if len(lines) < 64:
            lines.append(line[:1024])


def _repository_skill_overrides(cwd: Path) -> list[dict[str, Any]]:
    """Disable every repository-local Skill visible from a root-level role cwd."""

    skills_root = cwd / ".agents" / "skills"
    if not skills_root.is_dir():
        return []
    return [
        {"path": str(skill_file), "enabled": False}
        for skill_file in sorted(skills_root.rglob("SKILL.md"))
        if skill_file.is_file()
    ]


def _validate_schema(value: Any, schema: Mapping[str, Any], path: str = "$") -> None:
    expected_type = schema.get("type")
    if expected_type == "object":
        if not isinstance(value, dict):
            raise OrchestratorError("INVALID_ROLE_REPORT", f"{path} is not an object")
        required = schema.get("required", [])
        if any(name not in value for name in required):
            raise OrchestratorError("INVALID_ROLE_REPORT", f"{path} lacks required fields")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False and set(value) - set(properties):
            raise OrchestratorError("INVALID_ROLE_REPORT", f"{path} has extra fields")
        for name, child in properties.items():
            if name in value and isinstance(child, dict):
                _validate_schema(value[name], child, f"{path}.{name}")
    elif expected_type == "array":
        if not isinstance(value, list):
            raise OrchestratorError("INVALID_ROLE_REPORT", f"{path} is not an array")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                _validate_schema(item, item_schema, f"{path}[{index}]")
    elif expected_type == "string" and not isinstance(value, str):
        raise OrchestratorError("INVALID_ROLE_REPORT", f"{path} is not a string")
    elif expected_type == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
        raise OrchestratorError("INVALID_ROLE_REPORT", f"{path} is not an integer")
    elif expected_type == "boolean" and not isinstance(value, bool):
        raise OrchestratorError("INVALID_ROLE_REPORT", f"{path} is not a boolean")
    if "enum" in schema and value not in schema["enum"]:
        raise OrchestratorError("INVALID_ROLE_REPORT", f"{path} is outside enum")


class CodexRoleClient:
    """Launch one hook-disabled app-server process and one ephemeral thread per role."""

    def __init__(
        self,
        command: Sequence[str] | None = None,
        *,
        timeout_seconds: float = 120.0,
        role_execution: Mapping[str, RoleExecutionProfile] | None = None,
    ) -> None:
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._command = tuple(command) if command is not None else None
        if self._command is not None and (not self._command or any(not item for item in self._command)):
            raise ValueError("command must contain non-empty arguments")
        self._timeout_seconds = timeout_seconds
        self._role_execution = dict(role_execution or {})
        if any(
            not isinstance(name, str)
            or not name
            or not isinstance(profile, RoleExecutionProfile)
            for name, profile in self._role_execution.items()
        ):
            raise ValueError("role_execution must map names to RoleExecutionProfile")
        self._terminator = ProcessTreeTerminator()

    def _execution_profile(self, role: str) -> RoleExecutionProfile:
        return resolve_execution_profile(
            role, self._role_execution, self._timeout_seconds
        )

    @property
    def command(self) -> tuple[str, ...]:
        return self._command or tuple(_default_command())

    def invoke(self, request: RoleRequest) -> RoleInvocation:
        if request.sandbox not in {READ_ONLY, WORKSPACE_WRITE}:
            raise OrchestratorError("INVALID_ROLE_SANDBOX", request.sandbox)
        execution = self._execution_profile(request.role)
        if request.role in VALIDATION_EXECUTION_ROLES and (
            execution.model is None or execution.effort is None
        ):
            raise OrchestratorError("INVALID_ROLE_EXECUTION_PROFILE")
        launch_root: Path | None = None
        launch_cwd = request.cwd
        if request.isolate_project_instructions:
            launch_root = Path(tempfile.mkdtemp(prefix="trace-adv-appserver-"))
            launch_cwd = launch_root
        try:
            process = self._terminator.spawn(
                list(self.command),
                cwd=launch_cwd,
                env=_child_environment(),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="strict",
                bufsize=1,
            )
        except BaseException:
            if launch_root is not None:
                shutil.rmtree(launch_root, ignore_errors=True)
            raise
        if process.stdin is None or process.stdout is None or process.stderr is None:
            self._terminator.terminate(process)
            if launch_root is not None:
                shutil.rmtree(launch_root, ignore_errors=True)
            raise OrchestratorError("APP_SERVER_PIPE_FAILURE")

        messages: queue.Queue[str | None] = queue.Queue()
        stderr_lines: list[str] = []
        stdout_thread = threading.Thread(
            target=_read_lines, args=(process.stdout, messages), daemon=True
        )
        stderr_thread = threading.Thread(
            target=_drain_stderr, args=(process.stderr, stderr_lines), daemon=True
        )
        stdout_thread.start()
        stderr_thread.start()
        assert execution.timeout_seconds is not None
        deadline = time.monotonic() + execution.timeout_seconds
        pending: list[dict[str, Any]] = []
        result: RoleInvocation | None = None
        failure: BaseException | None = None
        try:
            self._send(
                process,
                {
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "clientInfo": {
                            "name": "trace-adv-orchestrator",
                            "title": "TRACE-ADV Orchestrator",
                            "version": "0.1.0",
                        },
                        "capabilities": {
                            "optOutNotificationMethods": list(
                                QUIET_NOTIFICATION_METHODS
                            )
                        },
                    },
                },
            )
            self._await_response(process, messages, 1, deadline, pending)
            self._send(process, {"method": "initialized", "params": {}})
            thread_params: dict[str, Any] = {
                "cwd": str(request.cwd),
                "ephemeral": True,
                "approvalPolicy": "never",
                "sandbox": request.sandbox,
                "serviceName": f"trace-adv-{request.role.lower()}",
                "baseInstructions": request.base_instructions,
            }
            if execution.model is not None:
                thread_params["model"] = execution.model
            if request.isolate_project_instructions:
                isolated_config: dict[str, Any] = {
                    "project_doc_max_bytes": 0,
                    "project_doc_fallback_filenames": [],
                    "projects": {
                        str(request.cwd): {"trust_level": "untrusted"}
                    },
                }
                skill_overrides = _repository_skill_overrides(request.cwd)
                if skill_overrides:
                    isolated_config["skills"] = {"config": skill_overrides}
                thread_params["config"] = isolated_config
            self._send(
                process,
                {
                    "id": 2,
                    "method": "thread/start",
                    "params": thread_params,
                },
            )
            thread_result = self._await_response(process, messages, 2, deadline, pending)
            thread = thread_result.get("thread")
            thread_id = thread.get("id") if isinstance(thread, dict) else None
            if not isinstance(thread_id, str) or not thread_id:
                raise OrchestratorError("APP_SERVER_PROTOCOL_ERROR", "missing thread id")

            prompt = canonical_json_bytes(
                {"schema": "trace_adv.role_input.v1", "role": request.role, "input": request.payload}
            ).decode("utf-8")
            turn_params: dict[str, Any] = {
                "threadId": thread_id,
                "input": [{"type": "text", "text": prompt}],
                "outputSchema": dict(request.output_schema),
            }
            if execution.effort is not None:
                turn_params["effort"] = execution.effort
            self._send(
                process,
                {
                    "id": 3,
                    "method": "turn/start",
                    "params": turn_params,
                },
            )
            turn_result = self._await_response(process, messages, 3, deadline, pending)
            turn = turn_result.get("turn")
            turn_id = turn.get("id") if isinstance(turn, dict) else None
            if not isinstance(turn_id, str) or not turn_id:
                raise OrchestratorError("APP_SERVER_PROTOCOL_ERROR", "missing turn id")

            final_messages: list[str] = []
            observable_events: list[Mapping[str, Any]] = []
            completed = False
            for event in pending:
                if self._process_event(
                    event, thread_id, turn_id, final_messages, observable_events
                ):
                    completed = True
                    break
            while not completed:
                event = self._next_message(process, messages, deadline)
                completed = self._process_event(
                    event, thread_id, turn_id, final_messages, observable_events
                )
            if len(final_messages) != 1:
                raise OrchestratorError("AMBIGUOUS_OR_MISSING_FINAL_MESSAGE")
            try:
                report = json.loads(final_messages[0])
            except json.JSONDecodeError as error:
                raise OrchestratorError("INVALID_ROLE_REPORT", "final message is not JSON") from error
            if not isinstance(report, dict):
                raise OrchestratorError("INVALID_ROLE_REPORT", "final report is not an object")
            _validate_schema(report, request.output_schema)
            result = RoleInvocation(
                role=request.role,
                thread_id=thread_id,
                turn_id=turn_id,
                report=report,
                observable_events=tuple(observable_events),
                requested_execution=execution.to_dict(),
            )
        except BaseException as error:
            failure = error
        finally:
            cleanup_failure = self._stop_process(process, stdout_thread, stderr_thread)
            if launch_root is not None:
                try:
                    shutil.rmtree(launch_root)
                except OSError as error:
                    if cleanup_failure is None:
                        cleanup_failure = OrchestratorError(
                            "ROLE_LAUNCH_ROOT_CLEANUP_FAILED", str(error)
                        )
            if failure is None and cleanup_failure is not None:
                failure = cleanup_failure
        if failure is not None:
            if isinstance(failure, OrchestratorError):
                raise failure
            raise OrchestratorError("APP_SERVER_FAILURE", str(failure)) from failure
        if result is None:
            raise OrchestratorError("APP_SERVER_FAILURE", "missing role result")
        return result

    @staticmethod
    def _send(process: subprocess.Popen[str], payload: Mapping[str, Any]) -> None:
        if process.stdin is None:
            raise OrchestratorError("APP_SERVER_STDIN_CLOSED")
        process.stdin.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
        process.stdin.flush()

    @staticmethod
    def _next_message(
        process: subprocess.Popen[str],
        messages: queue.Queue[str | None],
        deadline: float,
    ) -> dict[str, Any]:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise OrchestratorError("APP_SERVER_TIMEOUT")
        try:
            line = messages.get(timeout=remaining)
        except queue.Empty as error:
            raise OrchestratorError("APP_SERVER_TIMEOUT") from error
        if line is None:
            detail = f"exit={process.poll()}"
            raise OrchestratorError("APP_SERVER_EOF", detail)
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise OrchestratorError("APP_SERVER_PROTOCOL_ERROR", "invalid JSON line") from error
        if not isinstance(value, dict):
            raise OrchestratorError("APP_SERVER_PROTOCOL_ERROR", "message is not an object")
        if "id" in value and "method" in value:
            raise OrchestratorError("UNEXPECTED_SERVER_REQUEST")
        return value

    @classmethod
    def _await_response(
        cls,
        process: subprocess.Popen[str],
        messages: queue.Queue[str | None],
        request_id: int,
        deadline: float,
        pending: list[dict[str, Any]],
    ) -> dict[str, Any]:
        while True:
            message = cls._next_message(process, messages, deadline)
            if message.get("id") != request_id:
                pending.append(message)
                continue
            if "error" in message:
                raise OrchestratorError("APP_SERVER_REQUEST_FAILED")
            result = message.get("result")
            if not isinstance(result, dict):
                raise OrchestratorError("APP_SERVER_PROTOCOL_ERROR", "response lacks result")
            return result

    @staticmethod
    def _process_event(
        event: Mapping[str, Any],
        thread_id: str,
        turn_id: str,
        final_messages: list[str],
        observable_events: list[Mapping[str, Any]],
    ) -> bool:
        method = event.get("method")
        params = event.get("params")
        if not isinstance(method, str) or not isinstance(params, dict):
            raise OrchestratorError("APP_SERVER_PROTOCOL_ERROR", "invalid event")
        if method.startswith("item/"):
            if params.get("threadId") != thread_id or params.get("turnId") != turn_id:
                raise OrchestratorError("EVENT_CORRELATION_FAILED")
            item = params.get("item")
            if not isinstance(item, dict):
                raise OrchestratorError("APP_SERVER_PROTOCOL_ERROR", "item event lacks item")
            sanitized: dict[str, Any] = {
                "method": method,
                "thread_id": thread_id,
                "turn_id": turn_id,
                "item": {
                    key: item[key]
                    for key in ("id", "type", "status", "phase", "command", "exitCode")
                    if key in item
                },
            }
            if (
                method == "item/completed"
                and item.get("type") == "agentMessage"
                and item.get("phase") == "final_answer"
            ):
                text = item.get("text")
                if not isinstance(text, str):
                    raise OrchestratorError("INVALID_ROLE_REPORT", "agentMessage lacks text")
                sanitized["item"]["text"] = text
                final_messages.append(text)
            observable_events.append(sanitized)
            return False
        if method == "turn/completed":
            turn = params.get("turn")
            if params.get("threadId") != thread_id or not isinstance(turn, dict):
                raise OrchestratorError("EVENT_CORRELATION_FAILED")
            if turn.get("id") != turn_id:
                raise OrchestratorError("EVENT_CORRELATION_FAILED")
            if turn.get("status") != "completed":
                raise OrchestratorError("CHILD_TURN_NOT_COMPLETED")
            observable_events.append(
                {
                    "method": method,
                    "thread_id": thread_id,
                    "turn_id": turn_id,
                    "status": "completed",
                }
            )
            return True
        if method == "error":
            # App Server uses this notification for retryable transport status
            # as well as terminal failures. The authoritative terminal signal
            # is turn/completed; retain only the event class and no message.
            observable_events.append({"method": method})
            return False
        if method == "model/rerouted":
            raise OrchestratorError("MODEL_REROUTED")
        if method in SANITIZED_INFORMATIONAL_METHODS or method in QUIET_NOTIFICATION_METHODS:
            observable_events.append({"method": method})
            return False
        raise OrchestratorError("UNEXPECTED_APP_SERVER_EVENT", method)

    def _stop_process(
        self,
        process: subprocess.Popen[str],
        stdout_thread: threading.Thread,
        stderr_thread: threading.Thread,
    ) -> OrchestratorError | None:
        termination_failure: OrchestratorError | None = None
        try:
            if process.stdin is not None:
                process.stdin.close()
        except OSError as error:
            termination_failure = OrchestratorError(
                "ROLE_PROCESS_TERMINATION_FAILED", str(error)
            )
        try:
            if process.poll() is None:
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass
        except (OSError, subprocess.SubprocessError) as error:
            termination_failure = OrchestratorError(
                "ROLE_PROCESS_TERMINATION_FAILED", str(error)
            )
        try:
            tree_terminated = self._terminator.terminate(process)
        except (OSError, subprocess.SubprocessError):
            tree_terminated = False
        if not tree_terminated:
            termination_failure = OrchestratorError(
                "ROLE_PROCESS_TERMINATION_FAILED",
                "owned process container did not become empty",
            )
        try:
            stdout_thread.join(timeout=2)
            stderr_thread.join(timeout=2)
            if stdout_thread.is_alive() or stderr_thread.is_alive():
                termination_failure = OrchestratorError(
                    "ROLE_PROCESS_TERMINATION_FAILED"
                )
            if process.stdout is not None:
                process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()
        except OSError as error:
            termination_failure = OrchestratorError(
                "ROLE_PROCESS_TERMINATION_FAILED", str(error)
            )
        return termination_failure
