from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Mapping, Sequence

from .model import (
    Candidate,
    MeasurementReport,
    OrchestratorError,
    RoleInvocation,
    TaskContract,
    hash_json,
    sha256_bytes,
)
from .process_control import ProcessTreeTerminator


class GitRepository:
    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path).resolve()
        top = self.run("rev-parse", "--show-toplevel").stdout.decode("utf-8").strip()
        if Path(top).resolve() != self.path:
            raise OrchestratorError("REPOSITORY_ROOT_REQUIRED", top)

    def run(
        self,
        *args: str,
        cwd: Path | None = None,
        input_bytes: bytes | None = None,
        extra_env: Mapping[str, str] | None = None,
        deterministic: bool = False,
        check: bool = True,
    ) -> subprocess.CompletedProcess[bytes]:
        environment = os.environ.copy()
        if extra_env:
            environment.update(extra_env)
        command = ["git"]
        if deterministic:
            command.extend(
                ["-c", "core.autocrlf=false", "-c", "core.safecrlf=false"]
            )
        command.extend(args)
        completed = subprocess.run(
            command,
            cwd=cwd or self.path,
            env=environment,
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if check and completed.returncode != 0:
            detail = completed.stderr.decode("utf-8", errors="replace").strip()
            raise OrchestratorError("GIT_COMMAND_FAILED", f"git {' '.join(args)}: {detail}")
        return completed

    def resolve_commit(self, revision: str = "HEAD") -> str:
        value = self.run("rev-parse", "--verify", f"{revision}^{{commit}}").stdout
        return value.decode("ascii").strip()

    def head(self) -> str:
        return self.resolve_commit("HEAD")

    def is_clean(self) -> bool:
        return not self.run(
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
            extra_env={"GIT_OPTIONAL_LOCKS": "0"},
        ).stdout

    def new_worktree(self, base_commit: str, prefix: str) -> "WorktreeLease":
        root = Path(tempfile.mkdtemp(prefix=prefix))
        worktree = root / "worktree"
        try:
            self.run(
                "worktree",
                "add",
                "--detach",
                str(worktree),
                base_commit,
                deterministic=True,
            )
        except BaseException:
            shutil.rmtree(root, ignore_errors=True)
            raise
        return WorktreeLease(repository=self, root=root, path=worktree)

    def apply_patch(self, worktree: Path, patch: bytes, *, check_only: bool = False) -> None:
        if not patch:
            return
        arguments = ["apply", "--binary", "--whitespace=nowarn"]
        if check_only:
            arguments.append("--check")
        self.run(*arguments, cwd=worktree, input_bytes=patch)

    def apply_patch_to_index(self, worktree: Path, patch: bytes) -> None:
        if patch:
            self.run(
                "apply",
                "--binary",
                "--whitespace=nowarn",
                "--index",
                cwd=worktree,
                input_bytes=patch,
                deterministic=True,
            )

    def worktree_tree_id(self, worktree: Path) -> str:
        return self.run("write-tree", cwd=worktree).stdout.decode("ascii").strip()

    def worktree_matches_candidate(self, worktree: Path, tree_id: str) -> bool:
        if self.worktree_tree_id(worktree) != tree_id:
            return False
        if self.run("diff-files", "--quiet", cwd=worktree, check=False).returncode != 0:
            return False
        untracked = self.run(
            "ls-files", "--others", "--exclude-standard", "-z", cwd=worktree
        ).stdout
        return not untracked

    def changed_paths(self, old_tree: str, new_tree: str) -> tuple[str, ...]:
        raw = self.run("diff", "--name-only", "-z", old_tree, new_tree, "--").stdout
        return tuple(
            item.decode("utf-8", errors="surrogateescape")
            for item in raw.split(b"\0")
            if item
        )


class WorktreeLease:
    def __init__(self, repository: GitRepository, root: Path, path: Path) -> None:
        self.repository = repository
        self.root = root
        self.path = path
        self._closed = False

    def cleanup(self) -> None:
        if self._closed:
            return
        failure: OrchestratorError | None = None
        try:
            self.repository.run("worktree", "remove", "--force", str(self.path))
        except OrchestratorError as error:
            failure = error
        if failure is None:
            try:
                shutil.rmtree(self.root)
            except OSError as error:
                failure = OrchestratorError("WORKTREE_CLEANUP_FAILED", str(error))
        self._closed = failure is None
        if failure is not None:
            raise OrchestratorError("WORKTREE_CLEANUP_FAILED", failure.detail)


class CandidateBuilder:
    def __init__(self, repository: GitRepository) -> None:
        self.repository = repository

    def freeze(
        self,
        author_worktree: Path,
        base_commit: str,
        contract: TaskContract,
        author_result: RoleInvocation,
    ) -> Candidate:
        if self.repository.resolve_commit(base_commit) != base_commit:
            raise OrchestratorError("BASE_COMMIT_MISMATCH")
        with tempfile.TemporaryDirectory(prefix="trace-adv-index-") as index_root:
            index_path = str(Path(index_root) / "index")
            index_env = {"GIT_INDEX_FILE": index_path}
            self.repository.run(
                "read-tree",
                base_commit,
                cwd=author_worktree,
                extra_env=index_env,
                deterministic=True,
            )
            self.repository.run(
                "add",
                "-A",
                "--",
                ".",
                cwd=author_worktree,
                extra_env=index_env,
                deterministic=True,
            )
            tree_id = (
                self.repository.run(
                    "write-tree",
                    cwd=author_worktree,
                    extra_env=index_env,
                    deterministic=True,
                )
                .stdout.decode("ascii")
                .strip()
            )
            patch = self.repository.run(
                "diff",
                "--binary",
                "--full-index",
                "--no-color",
                "--no-ext-diff",
                "--find-renames=50%",
                "--cached",
                base_commit,
                "--",
                cwd=author_worktree,
                extra_env=index_env,
                deterministic=True,
            ).stdout

        manifest = {
            "schema": "trace_adv.candidate_manifest.v1",
            "request_sha256": sha256_bytes(contract.original_request.encode("utf-8")),
            "amendments_sha256": hash_json(list(contract.amendments)),
            "contract_sha256": contract.sha256,
            "base_commit": base_commit,
            "patch_sha256": sha256_bytes(patch),
            "author_final_sha256": hash_json(author_result.report),
            "observable_event_digest": author_result.observable_event_digest,
            "candidate_tree_id": tree_id,
        }
        candidate = Candidate(
            base_commit=base_commit,
            patch=patch,
            tree_id=tree_id,
            author_final=author_result.report,
            observable_event_digest=author_result.observable_event_digest,
            manifest=manifest,
            manifest_sha256=hash_json(manifest),
        )
        self.verify_reproduction(candidate, contract)
        return candidate

    def verify_reproduction(self, candidate: Candidate, contract: TaskContract) -> None:
        candidate.verify_binding(contract)
        if self.repository.resolve_commit(candidate.base_commit) != candidate.base_commit:
            raise OrchestratorError("BASE_COMMIT_MISMATCH")
        lease = self.repository.new_worktree(candidate.base_commit, "trace-adv-verify-")
        failure: BaseException | None = None
        try:
            self.repository.apply_patch_to_index(lease.path, candidate.patch)
            if not self.repository.worktree_matches_candidate(
                lease.path, candidate.tree_id
            ):
                raise OrchestratorError("CANDIDATE_TREE_MISMATCH")
        except BaseException as error:
            failure = error
        try:
            lease.cleanup()
        except BaseException as error:
            if failure is None:
                failure = error
        if failure is not None:
            raise failure


class MeasurementExecutor:
    def __init__(self, terminator: ProcessTreeTerminator | None = None) -> None:
        self.terminator = terminator or ProcessTreeTerminator()

    def run(
        self,
        repository: GitRepository,
        candidate: Candidate,
        contract: TaskContract,
        argv: Sequence[str],
        timeout_seconds: float,
    ) -> MeasurementReport:
        if not argv or any(not isinstance(item, str) or not item for item in argv):
            raise OrchestratorError("INVALID_MEASUREMENT_ARGV")
        if timeout_seconds <= 0:
            raise OrchestratorError("INVALID_MEASUREMENT_TIMEOUT")
        candidate.verify_binding(contract)
        before_hash = candidate.patch_sha256
        status = "BLOCKED"
        exit_code: int | None = None
        stdout = b""
        stderr = b""
        timed_out = False
        tree_terminated = False
        cleanup_succeeded = False
        code: str | None = None
        lease = repository.new_worktree(candidate.base_commit, "trace-adv-measure-")
        process: subprocess.Popen[bytes] | None = None
        try:
            repository.apply_patch_to_index(lease.path, candidate.patch)
            if not repository.worktree_matches_candidate(
                lease.path, candidate.tree_id
            ):
                raise OrchestratorError("CANDIDATE_TREE_MISMATCH")
            process = self.terminator.spawn(
                list(argv),
                cwd=lease.path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            try:
                stdout, stderr = process.communicate(timeout=timeout_seconds)
                exit_code = process.returncode
                status = "COMPLETED"
            except subprocess.TimeoutExpired as error:
                timed_out = True
                partial_stdout = error.output or b""
                partial_stderr = error.stderr or b""
                tree_terminated = self.terminator.terminate(process)
                if not tree_terminated and process.poll() is None:
                    try:
                        process.kill()
                        process.wait(timeout=3)
                    except (OSError, subprocess.SubprocessError):
                        pass
                try:
                    drained_stdout, drained_stderr = process.communicate(timeout=1)
                    stdout = drained_stdout or partial_stdout
                    stderr = drained_stderr or partial_stderr
                except subprocess.SubprocessError:
                    stdout, stderr = partial_stdout, partial_stderr
                status = "BLOCKED"
                code = (
                    "MEASUREMENT_TIMEOUT"
                    if tree_terminated
                    else "PROCESS_TREE_TERMINATION_FAILED"
                )
        except OrchestratorError as error:
            status = "BLOCKED"
            code = error.code
        except OSError as error:
            status = "BLOCKED"
            code = "MEASUREMENT_LAUNCH_FAILED"
            stderr = str(error).encode("utf-8", errors="replace")
        finally:
            if process is not None and not tree_terminated:
                tree_terminated = self.terminator.terminate(process)
            if not tree_terminated:
                status = "BLOCKED"
                code = "PROCESS_TREE_TERMINATION_FAILED"
            try:
                lease.cleanup()
                cleanup_succeeded = True
            except OrchestratorError:
                cleanup_succeeded = False
                status = "BLOCKED"
                code = "WORKTREE_CLEANUP_FAILED"

        after_hash = candidate.patch_sha256
        if before_hash != after_hash:
            status = "BLOCKED"
            code = "FROZEN_PATCH_MUTATED"
        return MeasurementReport(
            status=status,
            argv=tuple(argv),
            exit_code=exit_code,
            stdout=stdout.decode("utf-8", errors="replace"),
            stderr=stderr.decode("utf-8", errors="replace"),
            timed_out=timed_out,
            process_tree_terminated=tree_terminated,
            cleanup_succeeded=cleanup_succeeded,
            frozen_patch_sha256_before=before_hash,
            frozen_patch_sha256_after=after_hash,
            code=code,
        )
