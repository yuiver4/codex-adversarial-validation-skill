from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Callable, Mapping

from orchestrator.codex_client import RoleRequest
from orchestrator.model import RoleInvocation


PLAN_REPORT = {
    "summary": "bounded plan",
    "plan": ["write result.txt", "run measurement"],
    "action_summary": ["inspected contract", "proposed bounded edit"],
}
AUTHOR_REPORT = {
    "summary": "implemented candidate",
    "action_summary": ["wrote result.txt"],
}
TRACE_REPORT = {
    "p_proc": "PASS",
    "proposition": "observable actions support the reported process",
    "process_map": ["contract -> edit -> measurement"],
    "step_kill": "removing the edit event would leave the claim unsupported",
    "evidence": ["E1: bounded observable event"],
    "measurement": "bound measurement completed",
    "residual_risk": [],
}
AV_REPORT = {
    "challenged_proposition": "candidate fulfills the contract",
    "strongest_countercase": "the requested file could be missing",
    "evidence": ["measurement reads the requested file"],
    "requested_measurement": "measurement exits zero",
    "residual_attack_surface": [],
}


def judge_report(verdict: str = "PASS", scope: list[str] | None = None) -> dict[str, Any]:
    return {
        "verdict": verdict,
        "p_out": verdict,
        "p_task": verdict,
        "p_tech": verdict,
        "summary": "judge result",
        "findings": [],
        "revision_scope": scope or [],
    }


def git(path: Path, *args: str, input_bytes: bytes | None = None) -> bytes:
    result = subprocess.run(
        ["git", *args],
        cwd=path,
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr.decode("utf-8", errors="replace"))
    return result.stdout


def init_repo(path: Path) -> str:
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init")
    git(path, "config", "user.name", "TRACE Test")
    git(path, "config", "user.email", "trace@example.invalid")
    (path / "base.txt").write_text("base\n", encoding="utf-8")
    git(path, "add", "base.txt")
    git(path, "commit", "-m", "base")
    return git(path, "rev-parse", "HEAD").decode("ascii").strip()


class ScriptedRoleRunner:
    def __init__(
        self,
        reports: Mapping[str, Mapping[str, Any]] | None = None,
        writes: Mapping[str, Callable[[Path], None]] | None = None,
    ) -> None:
        self.reports = dict(reports or {})
        self.writes = dict(writes or {})
        self.requests: list[RoleRequest] = []
        self._counter = 0

    def invoke(self, request: RoleRequest) -> RoleInvocation:
        self.requests.append(request)
        self._counter += 1
        if request.role in self.writes:
            self.writes[request.role](request.cwd)
        report = dict(self.reports.get(request.role, self._default_report(request.role)))
        return RoleInvocation(
            role=request.role,
            thread_id=f"thread-{self._counter}",
            turn_id=f"turn-{self._counter}",
            report=report,
            observable_events=(
                {
                    "method": "item/completed",
                    "thread_id": f"thread-{self._counter}",
                    "turn_id": f"turn-{self._counter}",
                    "item": {"type": "agentMessage", "phase": "final_answer"},
                },
            ),
        )

    @staticmethod
    def _default_report(role: str) -> Mapping[str, Any]:
        if role in {"PLAN_AUTHOR", "PLAN_AUTHOR_DELTA"}:
            return PLAN_REPORT
        if role in {"AUTHOR_IMPLEMENT", "RESULT_AUTHOR_DELTA"}:
            return AUTHOR_REPORT
        if role in {"PLAN_TRACE", "RESULT_TRACE"}:
            return TRACE_REPORT
        if role in {"PLAN_AV", "RESULT_AV"}:
            return AV_REPORT
        return judge_report()


def standard_runner(
    reports: Mapping[str, Mapping[str, Any]] | None = None,
    writes: Mapping[str, Callable[[Path], None]] | None = None,
) -> ScriptedRoleRunner:
    merged_writes: dict[str, Callable[[Path], None]] = {
        "AUTHOR_IMPLEMENT": lambda path: (path / "result.txt").write_text(
            "candidate\n", encoding="utf-8"
        )
    }
    if writes:
        merged_writes.update(writes)
    return ScriptedRoleRunner(reports=reports, writes=merged_writes)
