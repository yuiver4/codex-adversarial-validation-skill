from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .codex_client import (
    VALIDATION_EXECUTION_ROLES,
    CodexRoleClient,
    RoleExecutionProfile,
    resolve_execution_profile,
)
from .model import OrchestratorError, PipelineState
from .pipeline import PipelineJob, TraceOrchestrator


ROLE_EXECUTION_NAMES = {
    "default",
    "validation",
    "PLAN_AUTHOR",
    "PLAN_TRACE",
    "PLAN_AV",
    "PLAN_JUDGE",
    "PLAN_AUTHOR_DELTA",
    "PLAN_TARGETED_RECHECK",
    "AUTHOR_IMPLEMENT",
    "RESULT_TRACE",
    "RESULT_AV",
    "RESULT_JUDGE",
    "RESULT_AUTHOR_DELTA",
    "RESULT_TARGETED_RECHECK",
}


def _load_role_execution(value: Any) -> dict[str, RoleExecutionProfile]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise OrchestratorError("INVALID_JOB_FILE", "role_execution must be an object")
    profiles: dict[str, RoleExecutionProfile] = {}
    allowed_fields = {"model", "effort", "timeout_seconds"}
    for role, raw_profile in value.items():
        if role not in ROLE_EXECUTION_NAMES or not isinstance(raw_profile, dict):
            raise OrchestratorError("INVALID_JOB_FILE", "invalid role_execution entry")
        if set(raw_profile) - allowed_fields:
            raise OrchestratorError("INVALID_JOB_FILE", "unknown role_execution field")
        timeout = raw_profile.get("timeout_seconds")
        if timeout is not None and (
            isinstance(timeout, bool) or not isinstance(timeout, (int, float))
        ):
            raise OrchestratorError("INVALID_JOB_FILE", "invalid role timeout")
        profiles[role] = RoleExecutionProfile(
            model=raw_profile.get("model"),
            effort=raw_profile.get("effort"),
            timeout_seconds=float(timeout) if timeout is not None else None,
        )
    return profiles


def _load_job(
    path: Path,
) -> tuple[PipelineJob, list[str] | None, float, dict[str, RoleExecutionProfile]]:
    try:
        value: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise OrchestratorError("INVALID_JOB_FILE", str(error)) from error
    if not isinstance(value, dict):
        raise OrchestratorError("INVALID_JOB_FILE", "root must be an object")
    repository_value = value.get("repository")
    request = value.get("original_request")
    argv = value.get("measurement_argv")
    amendments = value.get("amendments", [])
    command = value.get("app_server_command")
    if not isinstance(repository_value, str) or not isinstance(request, str):
        raise OrchestratorError("INVALID_JOB_FILE", "repository/request missing")
    if not isinstance(argv, list) or any(not isinstance(item, str) for item in argv):
        raise OrchestratorError("INVALID_JOB_FILE", "measurement_argv must be strings")
    if not isinstance(amendments, list) or any(not isinstance(item, str) for item in amendments):
        raise OrchestratorError("INVALID_JOB_FILE", "amendments must be strings")
    if command is not None and (
        not isinstance(command, list) or any(not isinstance(item, str) for item in command)
    ):
        raise OrchestratorError("INVALID_JOB_FILE", "app_server_command must be strings")
    repository = Path(repository_value)
    if not repository.is_absolute():
        repository = path.parent / repository
    role_timeout = float(value.get("role_timeout_seconds", 120.0))
    measurement_timeout = float(value.get("measurement_timeout_seconds", 120.0))
    role_execution = _load_role_execution(value.get("role_execution"))
    for role in VALIDATION_EXECUTION_ROLES:
        profile = resolve_execution_profile(role, role_execution, role_timeout)
        if profile.model is None or profile.effort is None:
            raise OrchestratorError(
                "INVALID_JOB_FILE",
                "validation roles require an explicit model and effort",
            )
    job = PipelineJob.create(
        repository,
        request,
        argv,
        amendments=amendments,
        base_revision=str(value.get("base_revision", "HEAD")),
        measurement_timeout_seconds=measurement_timeout,
    )
    return job, command, role_timeout, role_execution


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the minimal TRACE-ADV pipeline")
    parser.add_argument("--job", type=Path, required=True, help="local JSON job")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="apply the receipt-bound PASS candidate; omitted means dry-run",
    )
    parser.add_argument(
        "--include-role-reports",
        action="store_true",
        help=(
            "include structured role reports in local JSON output; may repeat "
            "private task content"
        ),
    )
    args = parser.parse_args(argv)
    try:
        job, command, role_timeout, role_execution = _load_job(args.job.resolve())
        client = CodexRoleClient(
            command,
            timeout_seconds=role_timeout,
            role_execution=role_execution,
        )
        outcome = TraceOrchestrator(client).run(job, apply=args.apply)
    except (OrchestratorError, ValueError) as error:
        code = error.code if isinstance(error, OrchestratorError) else "INVALID_JOB_FILE"
        print(json.dumps({"state": "BLOCKED", "code": code}, sort_keys=True))
        return 2
    print(
        json.dumps(
            outcome.to_dict(include_role_reports=args.include_role_reports),
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if outcome.state in {PipelineState.DRY_RUN, PipelineState.APPLIED} else 2


if __name__ == "__main__":
    raise SystemExit(main())
