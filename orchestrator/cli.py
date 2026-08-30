from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .codex_client import CodexRoleClient
from .model import OrchestratorError, PipelineState
from .pipeline import PipelineJob, TraceOrchestrator


def _load_job(path: Path) -> tuple[PipelineJob, list[str] | None, float]:
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
    job = PipelineJob.create(
        repository,
        request,
        argv,
        amendments=amendments,
        base_revision=str(value.get("base_revision", "HEAD")),
        measurement_timeout_seconds=measurement_timeout,
    )
    return job, command, role_timeout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the minimal TRACE-ADV pipeline")
    parser.add_argument("--job", type=Path, required=True, help="local JSON job")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="apply the receipt-bound PASS candidate; omitted means dry-run",
    )
    args = parser.parse_args(argv)
    try:
        job, command, role_timeout = _load_job(args.job.resolve())
        client = CodexRoleClient(command, timeout_seconds=role_timeout)
        outcome = TraceOrchestrator(client).run(job, apply=args.apply)
    except (OrchestratorError, ValueError) as error:
        code = error.code if isinstance(error, OrchestratorError) else "INVALID_JOB_FILE"
        print(json.dumps({"state": "BLOCKED", "code": code}, sort_keys=True))
        return 2
    print(json.dumps(outcome.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if outcome.state in {PipelineState.DRY_RUN, PipelineState.APPLIED} else 2


if __name__ == "__main__":
    raise SystemExit(main())
