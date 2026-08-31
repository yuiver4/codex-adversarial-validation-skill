from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator.codex_client import (
    VALIDATION_EXECUTION_ROLES,
    CodexRoleClient,
    READ_ONLY,
    RoleExecutionProfile,
    RoleRequest,
    resolve_execution_profile,
)
from orchestrator.model import OrchestratorError
from orchestrator.pipeline import AV_SCHEMA, TRACE_SCHEMA


def _windows_process_is_running(pid: int) -> bool:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetExitCodeProcess.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    handle = kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return False
    try:
        exit_code = wintypes.DWORD()
        return bool(kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))) and (
            exit_code.value == 259
        )
    finally:
        kernel32.CloseHandle(handle)


def trace_report() -> dict:
    return {
        "p_proc": "PASS",
        "proposition": "observable process claim",
        "process_map": ["read -> report"],
        "step_kill": "remove the read",
        "evidence": ["E1 read event"],
        "measurement": "not required for smoke",
        "residual_risk": [],
    }


class CodexRoleClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="trace-client-test-")
        self.root = Path(self.temporary.name)
        self.mapping_path = self.root / "mapping.json"
        self.log_path = self.root / "calls.jsonl"
        self.fake_server = Path(__file__).with_name("fake_app_server.py")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _invoke(
        self,
        report: dict,
        schema: dict,
        *,
        role: str = "PLAN_TRACE",
        scenario: str = "success",
        timeout: float = 3,
        isolate_project_instructions: bool = False,
        extra_command_arguments: list[str] | None = None,
        role_execution: dict[str, RoleExecutionProfile] | None = None,
    ):
        self.mapping_path.write_text(
            json.dumps({role: {"report": report}}), encoding="utf-8"
        )
        command = [
            sys.executable,
            str(self.fake_server),
            str(self.mapping_path),
            str(self.log_path),
            scenario,
            *(extra_command_arguments or []),
        ]
        if role_execution is None:
            role_execution = {
                "validation": RoleExecutionProfile(
                    model="test-model", effort="low"
                )
            }
        return CodexRoleClient(
            command,
            timeout_seconds=timeout,
            role_execution=role_execution,
        ).invoke(
            RoleRequest(
                role=role,
                payload={"task_contract": {"original_request": "x"}},
                output_schema=schema,
                cwd=self.root,
                sandbox=READ_ONLY,
                base_instructions="read-only test",
                isolate_project_instructions=isolate_project_instructions,
            )
        )

    def test_default_command_disables_hooks_and_uses_stdio_server(self) -> None:
        with patch("orchestrator.codex_client.shutil.which", return_value="codex"):
            self.assertEqual(
                CodexRoleClient().command,
                ("codex", "--disable", "hooks", "app-server", "--stdio"),
            )

    def test_non_finite_timeouts_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            CodexRoleClient(timeout_seconds=float("nan"))
        with self.assertRaises(ValueError):
            RoleExecutionProfile(timeout_seconds=float("inf"))

    def test_injected_server_receives_ephemeral_never_approved_read_only_thread(self) -> None:
        skill_file = self.root / ".agents" / "skills" / "candidate-poison" / "SKILL.md"
        skill_file.parent.mkdir(parents=True)
        skill_file.write_text("candidate-controlled instructions\n", encoding="utf-8")
        result = self._invoke(
            trace_report(), TRACE_SCHEMA, isolate_project_instructions=True
        )
        self.assertTrue(result.thread_id.startswith("fake-"))
        calls = [json.loads(line) for line in self.log_path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(calls), 1)
        thread = calls[0]["thread"]
        self.assertIs(thread["ephemeral"], True)
        self.assertEqual(thread["approvalPolicy"], "never")
        self.assertEqual(thread["sandbox"], "read-only")
        self.assertNotEqual(Path(calls[0]["server_cwd"]), self.root)
        self.assertEqual(Path(thread["cwd"]), self.root)
        self.assertEqual(thread["config"]["project_doc_max_bytes"], 0)
        self.assertEqual(
            thread["config"]["projects"][str(self.root)]["trust_level"],
            "untrusted",
        )
        self.assertEqual(
            thread["config"]["skills"]["config"],
            [{"path": str(skill_file), "enabled": False}],
        )
        self.assertIn(
            "remoteControl/status/changed",
            calls[0]["initialize"]["capabilities"]["optOutNotificationMethods"],
        )
        self.assertIn("output_schema", calls[0])

    def test_role_execution_profile_controls_model_effort_and_timeout(self) -> None:
        result = self._invoke(
            trace_report(),
            TRACE_SCHEMA,
            role_execution={
                "default": RoleExecutionProfile(
                    model="test-model",
                    effort="low",
                    timeout_seconds=2,
                ),
                "PLAN_TRACE": RoleExecutionProfile(effort="medium"),
            },
        )
        call = json.loads(self.log_path.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(call["thread"]["model"], "test-model")
        self.assertEqual(call["turn"]["effort"], "medium")
        self.assertEqual(
            result.requested_execution,
            {"model": "test-model", "effort": "medium", "timeout_seconds": 2},
        )

    def test_validation_group_is_explicit_and_exact_role_wins_fieldwise(self) -> None:
        profiles = {
            "default": RoleExecutionProfile(
                model="author-model", effort="low", timeout_seconds=41
            ),
            "validation": RoleExecutionProfile(
                model="gpt-5.6-sol", effort="high", timeout_seconds=19
            ),
            "RESULT_JUDGE": RoleExecutionProfile(
                model="user-selected-model", timeout_seconds=7
            ),
        }

        for role in VALIDATION_EXECUTION_ROLES - {"RESULT_JUDGE"}:
            with self.subTest(role=role):
                self.assertEqual(
                    resolve_execution_profile(role, profiles, 120).to_dict(),
                    {
                        "model": "gpt-5.6-sol",
                        "effort": "high",
                        "timeout_seconds": 19,
                    },
                )
        self.assertEqual(
            resolve_execution_profile("RESULT_JUDGE", profiles, 120).to_dict(),
            {
                "model": "user-selected-model",
                "effort": "high",
                "timeout_seconds": 7,
            },
        )
        self.assertEqual(
            resolve_execution_profile("AUTHOR_IMPLEMENT", profiles, 120).to_dict(),
            {"model": "author-model", "effort": "low", "timeout_seconds": 41},
        )

    def test_no_hidden_validation_model_is_selected(self) -> None:
        for role in VALIDATION_EXECUTION_ROLES:
            with self.subTest(role=role):
                profile = resolve_execution_profile(role, {}, 120)
                self.assertIsNone(profile.model)
                self.assertIsNone(profile.effort)
                self.assertEqual(profile.timeout_seconds, 120)

    def test_direct_validation_roles_require_explicit_model_and_effort(self) -> None:
        for role in VALIDATION_EXECUTION_ROLES:
            with self.subTest(role=role):
                with self.assertRaises(OrchestratorError) as caught:
                    self._invoke(
                        trace_report(),
                        TRACE_SCHEMA,
                        role=role,
                        role_execution={},
                    )
                self.assertEqual(
                    caught.exception.code, "INVALID_ROLE_EXECUTION_PROFILE"
                )
        self.assertFalse(self.log_path.exists())

    def test_event_ids_and_single_final_message_are_fail_closed(self) -> None:
        report = trace_report()
        for scenario, code in (
            ("wrong_correlation", "EVENT_CORRELATION_FAILED"),
            ("multiple_final", "AMBIGUOUS_OR_MISSING_FINAL_MESSAGE"),
        ):
            with self.subTest(scenario=scenario):
                with self.assertRaises(OrchestratorError) as caught:
                    self._invoke(report, TRACE_SCHEMA, scenario=scenario)
                self.assertEqual(caught.exception.code, code)

    def test_timeout_is_fail_closed_and_process_is_stopped(self) -> None:
        with self.assertRaises(OrchestratorError) as caught:
            self._invoke(
                trace_report(),
                TRACE_SCHEMA,
                scenario="hang",
                timeout=0.2,
            )
        self.assertEqual(caught.exception.code, "APP_SERVER_TIMEOUT")

    def test_role_timeout_overrides_longer_client_default(self) -> None:
        started = time.monotonic()
        with self.assertRaises(OrchestratorError) as caught:
            self._invoke(
                trace_report(),
                TRACE_SCHEMA,
                scenario="hang",
                timeout=5,
                role_execution={
                    "validation": RoleExecutionProfile(
                        model="test-model", effort="low"
                    ),
                    "PLAN_TRACE": RoleExecutionProfile(timeout_seconds=0.1)
                },
            )
        self.assertEqual(caught.exception.code, "APP_SERVER_TIMEOUT")
        self.assertLess(time.monotonic() - started, 2)

    @unittest.skipUnless(os.name == "nt", "Windows Job Object probe")
    def test_successful_app_server_cannot_leave_detached_child(self) -> None:
        survivor_path = self.root / "survivor.pid"
        self._invoke(
            trace_report(),
            TRACE_SCHEMA,
            scenario="success_with_survivor",
            extra_command_arguments=[str(survivor_path)],
        )
        survivor_pid = int(survivor_path.read_text(encoding="ascii"))
        self.assertFalse(_windows_process_is_running(survivor_pid))

    def test_retryable_error_notification_waits_for_terminal_turn(self) -> None:
        result = self._invoke(
            trace_report(), TRACE_SCHEMA, scenario="retryable_error"
        )
        self.assertEqual(result.report, trace_report())
        self.assertIn("error", [event["method"] for event in result.observable_events])

    def test_model_reroute_is_fail_closed(self) -> None:
        with self.assertRaises(OrchestratorError) as caught:
            self._invoke(trace_report(), TRACE_SCHEMA, scenario="model_rerouted")
        self.assertEqual(caught.exception.code, "MODEL_REROUTED")

    def test_mcp_startup_status_is_sanitized_and_does_not_block_turn(self) -> None:
        result = self._invoke(
            trace_report(), TRACE_SCHEMA, scenario="mcp_startup_status"
        )
        self.assertIn(
            "mcpServer/startupStatus/updated",
            [event["method"] for event in result.observable_events],
        )
        self.assertNotIn(
            "private-name-must-not-survive",
            json.dumps(result.observable_events),
        )

    def test_trace_and_adversary_cannot_emit_release_or_output_verdicts(self) -> None:
        forbidden = ["verdict", "p_out", "p_task", "p_tech", "release_verdict"]
        for field in forbidden:
            with self.subTest(role="TRACE", field=field):
                report = {**trace_report(), field: "PASS"}
                with self.assertRaises(OrchestratorError) as caught:
                    self._invoke(report, TRACE_SCHEMA)
                self.assertEqual(caught.exception.code, "INVALID_ROLE_REPORT")
            with self.subTest(role="AV", field=field):
                report = {
                    "challenged_proposition": "candidate claim",
                    "strongest_countercase": "countercase",
                    "evidence": [],
                    "requested_measurement": "test",
                    "residual_attack_surface": [],
                    field: "PASS",
                }
                with self.assertRaises(OrchestratorError) as caught:
                    self._invoke(report, AV_SCHEMA, role="PLAN_AV")
                self.assertEqual(caught.exception.code, "INVALID_ROLE_REPORT")


if __name__ == "__main__":
    unittest.main()
