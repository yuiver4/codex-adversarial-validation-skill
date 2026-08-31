from __future__ import annotations

import dataclasses
import sys
import tempfile
import unittest
from pathlib import Path

from orchestrator.codex_client import READ_ONLY, WORKSPACE_WRITE
from orchestrator.gitops import GitRepository
from orchestrator.model import OrchestratorError, PipelineState, TaskContract, Verdict, hash_json
from orchestrator.pipeline import (
    PipelineJob,
    ReleaseGate,
    TraceOrchestrator,
    make_release_receipt,
)
from orchestrator.tests.helpers import AUTHOR_REPORT, PLAN_REPORT, judge_report, standard_runner


class PipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="trace-pipeline-test-")
        self.root = Path(self.temporary.name) / "repo"
        from orchestrator.tests.helpers import init_repo

        init_repo(self.root)
        self.job = PipelineJob.create(
            self.root,
            "create result.txt through the reviewed pipeline",
            [sys.executable, "-c", "from pathlib import Path; print(Path('result.txt').read_text())"],
            amendments=["do not modify the target before release"],
            measurement_timeout_seconds=5,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _dry_outcome(self):
        runner = standard_runner()
        outcome = TraceOrchestrator(runner).run(self.job)
        self.assertEqual(outcome.state, PipelineState.DRY_RUN, outcome.to_dict())
        return runner, outcome

    def _target_snapshot(self) -> dict[str, bytes]:
        return {
            str(path.relative_to(self.root)): path.read_bytes()
            for path in self.root.rglob("*")
            if path.is_file() and ".git" not in path.parts
        }

    def test_plan_must_pass_before_any_workspace_write_role(self) -> None:
        runner = standard_runner(reports={"PLAN_JUDGE": judge_report("REJECT")})
        outcome = TraceOrchestrator(runner).run(self.job)
        self.assertEqual(outcome.state, PipelineState.BLOCKED)
        self.assertEqual(outcome.code, "PLAN_REJECT")
        self.assertNotIn("AUTHOR_IMPLEMENT", [item.role for item in runner.requests])
        self.assertTrue(all(item.sandbox == READ_ONLY for item in runner.requests))
        self.assertFalse((self.root / "result.txt").exists())

    def test_dirty_target_blocks_before_any_role(self) -> None:
        (self.root / "dirty.txt").write_text("dirty\n", encoding="utf-8")
        runner = standard_runner()
        outcome = TraceOrchestrator(runner).run(self.job)
        self.assertEqual(outcome.state, PipelineState.BLOCKED)
        self.assertEqual(outcome.code, "TARGET_NOT_CLEAN")
        self.assertEqual(runner.requests, [])

    def test_roles_use_distinct_threads_correct_sandboxes_and_minimal_inputs(self) -> None:
        runner, outcome = self._dry_outcome()
        expected_roles = {
            "PLAN_AUTHOR",
            "PLAN_TRACE",
            "PLAN_AV",
            "PLAN_JUDGE",
            "AUTHOR_IMPLEMENT",
            "RESULT_TRACE",
            "RESULT_AV",
            "RESULT_JUDGE",
        }
        self.assertEqual(set(outcome.roles), expected_roles)
        thread_ids = [item.thread_id for item in outcome.roles.values()]
        self.assertEqual(len(thread_ids), len(set(thread_ids)))
        requests = {item.role: item for item in runner.requests}
        self.assertEqual(requests["PLAN_AUTHOR"].sandbox, READ_ONLY)
        self.assertEqual(requests["AUTHOR_IMPLEMENT"].sandbox, WORKSPACE_WRITE)
        self.assertFalse(requests["PLAN_AUTHOR"].isolate_project_instructions)
        self.assertFalse(requests["AUTHOR_IMPLEMENT"].isolate_project_instructions)
        for role in expected_roles - {"AUTHOR_IMPLEMENT"}:
            self.assertEqual(requests[role].sandbox, READ_ONLY)
        for role in expected_roles - {"PLAN_AUTHOR", "AUTHOR_IMPLEMENT"}:
            self.assertTrue(requests[role].isolate_project_instructions)
            self.assertIn("repository-local skills", requests[role].base_instructions)

        self.assertEqual(
            set(requests["PLAN_AUTHOR"].payload),
            {"task_contract", "base_commit", "parent_evidence"},
        )
        self.assertEqual(
            requests["PLAN_AUTHOR"].payload["parent_evidence"]["measurement_executor"],
            {"configured": True, "timeout_seconds": 5},
        )
        parent_boundary = requests["PLAN_AV"].payload["parent_evidence"][
            "responsibility_boundary"
        ]
        self.assertTrue(parent_boundary["author"])
        self.assertTrue(parent_boundary["parent_orchestrator"])
        self.assertNotIn(
            "measurement_plan", requests["PLAN_AV"].payload["parent_evidence"]
        )
        self.assertNotIn(
            "measurement_argv", requests["PLAN_AV"].payload["parent_evidence"]
        )
        self.assertEqual(
            set(requests["PLAN_AV"].payload),
            {"task_contract", "candidate_plan", "parent_evidence"},
        )
        self.assertEqual(
            set(requests["PLAN_AV"].payload["candidate_plan"]),
            {"summary", "plan"},
        )
        self.assertNotIn(
            "action_summary", requests["PLAN_AV"].payload["candidate_plan"]
        )
        self.assertEqual(
            set(requests["PLAN_JUDGE"].payload),
            {"task_contract", "candidate_identity", "reports", "parent_evidence"},
        )
        self.assertEqual(
            requests["PLAN_JUDGE"].output_schema["properties"]["revision_scope"]["items"]["enum"],
            ["summary", "plan"],
        )
        self.assertEqual(
            set(requests["AUTHOR_IMPLEMENT"].payload["accepted_plan"]),
            {"summary", "plan"},
        )

        self.assertEqual(
            set(requests["RESULT_TRACE"].payload),
            {"task_contract", "candidate_identity", "observable_events", "action_summary"},
        )
        self.assertEqual(
            set(requests["RESULT_AV"].payload),
            {"task_contract", "candidate_identity", "measurement"},
        )
        self.assertNotEqual(requests["RESULT_AV"].cwd, self.root)
        self.assertEqual(requests["RESULT_TRACE"].cwd, requests["RESULT_AV"].cwd)
        self.assertNotIn("author", requests["RESULT_AV"].payload)
        self.assertNotIn("trace", requests["RESULT_AV"].payload)
        self.assertEqual(
            requests["RESULT_AV"].payload["measurement"]["argv"],
            list(self.job.measurement_argv),
        )
        self.assertIn("orchestrated-adversary", requests["RESULT_AV"].base_instructions)
        self.assertEqual(
            set(requests["RESULT_JUDGE"].payload),
            {"task_contract", "candidate_identity", "reports", "measurement"},
        )
        self.assertNotIn("candidate_patch", requests["RESULT_JUDGE"].payload)
        self.assertNotIn("author", requests["RESULT_JUDGE"].payload)

        trace_properties = set(requests["RESULT_TRACE"].output_schema["properties"])
        av_properties = set(requests["RESULT_AV"].output_schema["properties"])
        judge_properties = set(requests["RESULT_JUDGE"].output_schema["properties"])
        self.assertEqual(
            trace_properties,
            {
                "p_proc",
                "proposition",
                "process_map",
                "step_kill",
                "evidence",
                "measurement",
                "residual_risk",
            },
        )
        self.assertNotIn("verdict", av_properties)
        self.assertNotIn("release_verdict", av_properties)
        self.assertIn("verdict", judge_properties)
        self.assertTrue({"p_out", "p_task", "p_tech"}.issubset(judge_properties))
        self.assertIn("revision_scope", judge_properties)

    def test_plan_revise_uses_exact_top_level_field_scope(self) -> None:
        revised_plan = {
            **PLAN_REPORT,
            "plan": [*PLAN_REPORT["plan"], "verify exact bytes"],
            "action_summary": ["revised plan process only"],
        }
        runner = standard_runner(
            reports={
                "PLAN_JUDGE": judge_report("REVISE", ["plan"]),
                "PLAN_AUTHOR_DELTA": revised_plan,
                "PLAN_TARGETED_RECHECK": judge_report("PASS"),
            }
        )
        outcome = TraceOrchestrator(runner).run(self.job)
        self.assertEqual(outcome.state, PipelineState.DRY_RUN, outcome.to_dict())
        self.assertEqual(len(outcome.revisions), 1)
        self.assertEqual(outcome.revisions[0].gate, "PLAN")
        self.assertEqual(outcome.revisions[0].scope, ("plan",))
        self.assertEqual(outcome.revisions[0].delta, ("plan",))

    def test_default_is_dry_run_and_apply_is_explicit(self) -> None:
        _, dry = self._dry_outcome()
        self.assertEqual(dry.release["status"], "DRY_RUN")
        self.assertFalse(dry.release["mutated"])
        self.assertFalse((self.root / "result.txt").exists())

        applied = TraceOrchestrator(standard_runner()).run(self.job, apply=True)
        self.assertEqual(applied.state, PipelineState.APPLIED, applied.to_dict())
        self.assertTrue(applied.release["mutated"])
        self.assertEqual((self.root / "result.txt").read_text(encoding="utf-8"), "candidate\n")

    def test_candidate_and_receipt_tamper_missing_and_stale_receipts_do_not_mutate(self) -> None:
        _, outcome = self._dry_outcome()
        repository = GitRepository(self.root)
        contract = TaskContract.create(self.job.original_request, self.job.amendments)
        gate = ReleaseGate()
        candidate = outcome.candidate
        measurement = outcome.measurement
        self.assertIsNotNone(candidate)
        self.assertIsNotNone(measurement)
        before = self._target_snapshot()

        cases: list[tuple[str, object, object]] = []
        cases.append(("MISSING_RELEASE_RECEIPT", candidate, None))

        tampered_receipt = dict(outcome.receipt)
        tampered_receipt["candidate_patch_sha256"] = "0" * 64
        cases.append(("RELEASE_RECEIPT_TAMPERED", candidate, tampered_receipt))

        stale_receipt = dict(outcome.receipt)
        stale_receipt.pop("receipt_sha256")
        stale_receipt["contract_sha256"] = "1" * 64
        stale_receipt["receipt_sha256"] = hash_json(stale_receipt)
        cases.append(("STALE_RELEASE_RECEIPT", candidate, stale_receipt))

        tampered_candidate = dataclasses.replace(candidate, patch=candidate.patch + b"\n# tamper\n")
        cases.append(("CANDIDATE_BINDING_MISMATCH", tampered_candidate, outcome.receipt))

        for expected_code, supplied_candidate, receipt in cases:
            with self.subTest(code=expected_code):
                with self.assertRaises(OrchestratorError) as caught:
                    gate.release(
                        repository,
                        contract,
                        supplied_candidate,
                        measurement,
                        outcome.roles,
                        outcome.revisions,
                        Verdict.PASS,
                        receipt,
                        apply=True,
                    )
                self.assertEqual(caught.exception.code, expected_code)
                self.assertEqual(self._target_snapshot(), before)

    def test_dirty_target_precondition_fails_without_further_mutation(self) -> None:
        _, outcome = self._dry_outcome()
        (self.root / "dirty.txt").write_text("keep exactly\n", encoding="utf-8")
        before = self._target_snapshot()
        contract = TaskContract.create(self.job.original_request, self.job.amendments)
        with self.assertRaises(OrchestratorError) as caught:
            ReleaseGate().release(
                GitRepository(self.root),
                contract,
                outcome.candidate,
                outcome.measurement,
                outcome.roles,
                outcome.revisions,
                Verdict.PASS,
                outcome.receipt,
                apply=True,
            )
        self.assertEqual(caught.exception.code, "TARGET_NOT_CLEAN")
        self.assertEqual(self._target_snapshot(), before)

    def test_every_non_pass_verdict_blocks_release(self) -> None:
        _, outcome = self._dry_outcome()
        repository = GitRepository(self.root)
        contract = TaskContract.create(self.job.original_request, self.job.amendments)
        before = self._target_snapshot()
        for verdict in Verdict:
            if verdict is Verdict.PASS:
                continue
            with self.subTest(verdict=verdict.value):
                with self.assertRaises(OrchestratorError) as caught:
                    ReleaseGate().release(
                        repository,
                        contract,
                        outcome.candidate,
                        outcome.measurement,
                        outcome.roles,
                        outcome.revisions,
                        verdict,
                        outcome.receipt,
                        apply=True,
                    )
                self.assertEqual(caught.exception.code, "NON_PASS_RELEASE_BLOCKED")
                self.assertEqual(self._target_snapshot(), before)

    def test_judge_cannot_pass_when_a_bound_claim_fails(self) -> None:
        inconsistent = judge_report("PASS")
        inconsistent["p_task"] = "REJECT"
        runner = standard_runner(reports={"PLAN_JUDGE": inconsistent})
        outcome = TraceOrchestrator(runner).run(self.job)
        self.assertEqual(outcome.state, PipelineState.BLOCKED)
        self.assertEqual(outcome.code, "INCONSISTENT_JUDGE_VERDICT")
        self.assertNotIn("AUTHOR_IMPLEMENT", [item.role for item in runner.requests])

    def test_result_adversary_cannot_mutate_materialized_candidate(self) -> None:
        runner = standard_runner(
            writes={
                "RESULT_AV": lambda path: (path / "result.txt").write_text(
                    "reviewer mutation\n", encoding="utf-8"
                )
            }
        )
        outcome = TraceOrchestrator(runner).run(self.job)
        self.assertEqual(outcome.state, PipelineState.BLOCKED)
        self.assertEqual(outcome.code, "REVIEW_WORKTREE_MUTATED")
        self.assertFalse((self.root / "result.txt").exists())

    def test_receipt_rejects_duplicate_threads_and_invalid_measurement(self) -> None:
        _, outcome = self._dry_outcome()
        contract = TaskContract.create(self.job.original_request, self.job.amendments)
        duplicated_roles = dict(outcome.roles)
        duplicated_roles["RESULT_JUDGE"] = dataclasses.replace(
            duplicated_roles["RESULT_JUDGE"],
            thread_id=duplicated_roles["RESULT_AV"].thread_id,
        )
        with self.assertRaises(OrchestratorError) as duplicate:
            make_release_receipt(
                contract,
                outcome.candidate,
                outcome.measurement,
                duplicated_roles,
                outcome.revisions,
                Verdict.PASS,
            )
        self.assertEqual(duplicate.exception.code, "ROLE_THREAD_REUSED")

        blocked_measurement = dataclasses.replace(
            outcome.measurement,
            status="BLOCKED",
            code="MEASUREMENT_TIMEOUT",
            timed_out=True,
        )
        with self.assertRaises(OrchestratorError) as blocked:
            make_release_receipt(
                contract,
                outcome.candidate,
                blocked_measurement,
                outcome.roles,
                outcome.revisions,
                Verdict.PASS,
            )
        self.assertEqual(blocked.exception.code, "INVALID_MEASUREMENT_EVIDENCE")

        failed_measurement = dataclasses.replace(
            outcome.measurement,
            exit_code=1,
            stderr="tests failed",
        )
        with self.assertRaises(OrchestratorError) as failed:
            make_release_receipt(
                contract,
                outcome.candidate,
                failed_measurement,
                outcome.roles,
                outcome.revisions,
                Verdict.PASS,
            )
        self.assertEqual(failed.exception.code, "INVALID_MEASUREMENT_EVIDENCE")

        unverifiable_tree = dataclasses.replace(
            outcome.measurement,
            process_tree_terminated=False,
        )
        with self.assertRaises(OrchestratorError) as unverifiable:
            make_release_receipt(
                contract,
                outcome.candidate,
                unverifiable_tree,
                outcome.roles,
                outcome.revisions,
                Verdict.PASS,
            )
        self.assertEqual(unverifiable.exception.code, "INVALID_MEASUREMENT_EVIDENCE")

        mismatched_roles = dict(outcome.roles)
        mismatched_roles["RESULT_JUDGE"] = dataclasses.replace(
            mismatched_roles["RESULT_JUDGE"], report=judge_report("REJECT")
        )
        with self.assertRaises(OrchestratorError) as mismatch:
            make_release_receipt(
                contract,
                outcome.candidate,
                outcome.measurement,
                mismatched_roles,
                outcome.revisions,
                Verdict.PASS,
            )
        self.assertEqual(mismatch.exception.code, "JUDGE_VERDICT_MISMATCH")

    def test_revise_allows_one_delta_and_one_targeted_recheck_only(self) -> None:
        reports = {
            "RESULT_JUDGE": judge_report("REVISE", ["result.txt"]),
            "RESULT_TARGETED_RECHECK": judge_report("PASS"),
        }
        runner = standard_runner(
            reports=reports,
            writes={
                "RESULT_AUTHOR_DELTA": lambda path: (path / "result.txt").write_text(
                    "revised\n", encoding="utf-8"
                )
            },
        )
        outcome = TraceOrchestrator(runner).run(self.job)
        self.assertEqual(outcome.state, PipelineState.DRY_RUN, outcome.to_dict())
        roles = [item.role for item in runner.requests]
        self.assertEqual(roles.count("RESULT_AUTHOR_DELTA"), 1)
        self.assertEqual(roles.count("RESULT_TARGETED_RECHECK"), 1)
        self.assertEqual(roles.count("RESULT_TRACE"), 1)
        self.assertEqual(roles.count("RESULT_AV"), 1)
        self.assertEqual(len(outcome.revisions), 1)
        self.assertEqual(outcome.revisions[0].scope, ("result.txt",))

        second_revise_runner = standard_runner(
            reports={
                "RESULT_JUDGE": judge_report("REVISE", ["result.txt"]),
                "RESULT_TARGETED_RECHECK": judge_report("REVISE", ["result.txt"]),
            },
            writes={
                "RESULT_AUTHOR_DELTA": lambda path: (path / "result.txt").write_text(
                    "revised again\n", encoding="utf-8"
                )
            },
        )
        blocked = TraceOrchestrator(second_revise_runner).run(self.job)
        self.assertEqual(blocked.state, PipelineState.BLOCKED)
        self.assertEqual(
            [item.role for item in second_revise_runner.requests].count("RESULT_AUTHOR_DELTA"),
            1,
        )

    def test_out_of_scope_delta_requires_full_review_without_starting_one(self) -> None:
        runner = standard_runner(
            reports={"RESULT_JUDGE": judge_report("REVISE", ["result.txt"])},
            writes={
                "RESULT_AUTHOR_DELTA": lambda path: (path / "outside.txt").write_text(
                    "outside\n", encoding="utf-8"
                )
            },
        )
        outcome = TraceOrchestrator(runner).run(self.job)
        self.assertEqual(outcome.state, PipelineState.FULL_REVIEW_REQUIRED)
        self.assertEqual(outcome.code, "FULL_REVIEW_REQUIRED")
        roles = [item.role for item in runner.requests]
        self.assertEqual(roles.count("RESULT_AUTHOR_DELTA"), 1)
        self.assertNotIn("RESULT_TARGETED_RECHECK", roles)
        self.assertEqual(roles.count("RESULT_TRACE"), 1)
        self.assertEqual(roles.count("RESULT_AV"), 1)
        self.assertIsNone(outcome.receipt)


if __name__ == "__main__":
    unittest.main()
