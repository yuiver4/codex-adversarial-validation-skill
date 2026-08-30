from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from orchestrator.cli import main
from orchestrator.tests.helpers import (
    AUTHOR_REPORT,
    AV_REPORT,
    PLAN_REPORT,
    TRACE_REPORT,
    init_repo,
    judge_report,
)


class CliVerticalSliceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="trace-cli-test-")
        self.root = Path(self.temporary.name)
        self.repository = self.root / "repo"
        init_repo(self.repository)
        self.mapping = self.root / "mapping.json"
        self.calls = self.root / "calls.jsonl"
        self.job = self.root / "job.json"
        fake_server = Path(__file__).with_name("fake_app_server.py")
        reports = {
            "PLAN_AUTHOR": {"report": PLAN_REPORT},
            "PLAN_TRACE": {"report": TRACE_REPORT},
            "PLAN_AV": {"report": AV_REPORT},
            "PLAN_JUDGE": {"report": judge_report()},
            "AUTHOR_IMPLEMENT": {
                "report": AUTHOR_REPORT,
                "writes": {"result.txt": "candidate\n"},
            },
            "RESULT_TRACE": {"report": TRACE_REPORT},
            "RESULT_AV": {"report": AV_REPORT},
            "RESULT_JUDGE": {"report": judge_report()},
        }
        self.mapping.write_text(json.dumps(reports), encoding="utf-8")
        job = {
            "repository": str(self.repository),
            "original_request": "create result.txt through the reviewed pipeline",
            "amendments": [],
            "base_revision": "HEAD",
            "measurement_argv": [
                sys.executable,
                "-c",
                "from pathlib import Path; print(Path('result.txt').read_text())",
            ],
            "role_timeout_seconds": 5,
            "measurement_timeout_seconds": 5,
            "app_server_command": [
                sys.executable,
                str(fake_server),
                str(self.mapping),
                str(self.calls),
            ],
        }
        self.job.write_text(json.dumps(job), encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _run(self, *extra: str) -> dict:
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main(["--job", str(self.job), *extra])
        self.assertEqual(exit_code, 0, output.getvalue())
        return json.loads(output.getvalue())

    def test_dry_run_then_explicit_apply(self) -> None:
        dry = self._run()
        self.assertEqual(dry["state"], "DRY_RUN")
        self.assertFalse((self.repository / "result.txt").exists())
        self.assertIsNotNone(dry["receipt"])

        applied = self._run("--apply")
        self.assertEqual(applied["state"], "APPLIED")
        self.assertEqual(
            (self.repository / "result.txt").read_text(encoding="utf-8"),
            "candidate\n",
        )
        calls = [
            json.loads(line)
            for line in self.calls.read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(len(calls), 16)
        self.assertEqual(len({call["thread_id"] for call in calls}), 16)


if __name__ == "__main__":
    unittest.main()
