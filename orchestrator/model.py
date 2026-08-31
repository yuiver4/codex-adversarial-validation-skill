from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence


class OrchestratorError(RuntimeError):
    """A fail-closed orchestration error with a stable machine code."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


class Verdict(str, Enum):
    PASS = "PASS"
    PASS_WITH_CONDITIONS = "PASS WITH CONDITIONS"
    UNVERIFIED = "UNVERIFIED"
    REVISE = "REVISE"
    REJECT = "REJECT"


class PipelineState(str, Enum):
    INIT = "INIT"
    PLAN_AUTHOR = "PLAN_AUTHOR"
    PLAN_TRACE = "PLAN_TRACE"
    PLAN_AV = "PLAN_AV"
    PLAN_JUDGE = "PLAN_JUDGE"
    PLAN_AUTHOR_DELTA = "PLAN_AUTHOR_DELTA"
    PLAN_TARGETED_RECHECK = "PLAN_TARGETED_RECHECK"
    AUTHOR_IMPLEMENT = "AUTHOR_IMPLEMENT"
    CANDIDATE_FREEZE = "CANDIDATE_FREEZE"
    MEASUREMENT = "MEASUREMENT"
    RESULT_TRACE = "RESULT_TRACE"
    RESULT_AV = "RESULT_AV"
    RESULT_JUDGE = "RESULT_JUDGE"
    RESULT_AUTHOR_DELTA = "RESULT_AUTHOR_DELTA"
    RESULT_TARGETED_RECHECK = "RESULT_TARGETED_RECHECK"
    RELEASE_GATE = "RELEASE_GATE"
    DRY_RUN = "DRY_RUN"
    APPLIED = "APPLIED"
    BLOCKED = "BLOCKED"
    FULL_REVIEW_REQUIRED = "FULL_REVIEW_REQUIRED"


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def hash_json(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


@dataclass(frozen=True)
class TaskContract:
    original_request: str
    amendments: tuple[str, ...] = ()

    @classmethod
    def create(cls, original_request: str, amendments: Sequence[str] = ()) -> "TaskContract":
        if not original_request:
            raise OrchestratorError("INVALID_TASK_CONTRACT", "original request is empty")
        if any(not isinstance(item, str) or not item for item in amendments):
            raise OrchestratorError("INVALID_TASK_CONTRACT", "amendments must be non-empty strings")
        return cls(original_request=original_request, amendments=tuple(amendments))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "trace_adv.task_contract.v1",
            "original_request": self.original_request,
            "amendments": list(self.amendments),
        }

    @property
    def sha256(self) -> str:
        return hash_json(self.to_dict())


@dataclass(frozen=True)
class RoleInvocation:
    role: str
    thread_id: str
    turn_id: str
    report: Mapping[str, Any]
    observable_events: tuple[Mapping[str, Any], ...]
    requested_execution: Mapping[str, Any] = field(default_factory=dict)

    @property
    def report_sha256(self) -> str:
        return hash_json(self.report)

    @property
    def observable_event_digest(self) -> str:
        return hash_json(list(self.observable_events))


@dataclass(frozen=True)
class Candidate:
    base_commit: str
    patch: bytes
    tree_id: str
    author_final: Mapping[str, Any]
    observable_event_digest: str
    manifest: Mapping[str, Any]
    manifest_sha256: str

    @property
    def patch_sha256(self) -> str:
        return sha256_bytes(self.patch)

    @property
    def identity(self) -> dict[str, str]:
        return {
            "base_commit": self.base_commit,
            "tree_id": self.tree_id,
            "patch_sha256": self.patch_sha256,
            "manifest_sha256": self.manifest_sha256,
        }

    def verify_binding(self, contract: TaskContract) -> None:
        manifest = dict(self.manifest)
        expected_manifest_hash = hash_json(manifest)
        if expected_manifest_hash != self.manifest_sha256:
            raise OrchestratorError("CANDIDATE_MANIFEST_TAMPERED")
        expected = {
            "schema": "trace_adv.candidate_manifest.v1",
            "request_sha256": sha256_bytes(contract.original_request.encode("utf-8")),
            "amendments_sha256": hash_json(list(contract.amendments)),
            "contract_sha256": contract.sha256,
            "base_commit": self.base_commit,
            "patch_sha256": self.patch_sha256,
            "author_final_sha256": hash_json(self.author_final),
            "observable_event_digest": self.observable_event_digest,
            "candidate_tree_id": self.tree_id,
        }
        if manifest != expected:
            raise OrchestratorError("CANDIDATE_BINDING_MISMATCH")


@dataclass(frozen=True)
class MeasurementReport:
    status: str
    argv: tuple[str, ...]
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool
    process_tree_terminated: bool
    cleanup_succeeded: bool
    frozen_patch_sha256_before: str
    frozen_patch_sha256_after: str
    code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "trace_adv.measurement.v1",
            "status": self.status,
            "argv": list(self.argv),
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "timed_out": self.timed_out,
            "process_tree_terminated": self.process_tree_terminated,
            "cleanup_succeeded": self.cleanup_succeeded,
            "frozen_patch_sha256_before": self.frozen_patch_sha256_before,
            "frozen_patch_sha256_after": self.frozen_patch_sha256_after,
            "code": self.code,
        }

    @property
    def sha256(self) -> str:
        return hash_json(self.to_dict())


@dataclass(frozen=True)
class RevisionRecord:
    gate: str
    scope: tuple[str, ...]
    delta: tuple[str, ...]
    delta_sha256: str
    recheck_role: str
    recheck_thread_id: str
    recheck_report_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate": self.gate,
            "scope": list(self.scope),
            "delta": list(self.delta),
            "delta_sha256": self.delta_sha256,
            "recheck_role": self.recheck_role,
            "recheck_thread_id": self.recheck_thread_id,
            "recheck_report_sha256": self.recheck_report_sha256,
        }


def require_string_list(value: Any, code: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise OrchestratorError(code)
    return tuple(value)


def ensure_within_scope(delta: Sequence[str], scope: Sequence[str]) -> bool:
    """Use exact paths/keys or directory prefixes; glob interpretation is intentionally absent."""

    if not scope:
        return False
    for changed in delta:
        if not any(changed == allowed or changed.startswith(allowed.rstrip("/") + "/") for allowed in scope):
            return False
    return True


def absolute_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()
