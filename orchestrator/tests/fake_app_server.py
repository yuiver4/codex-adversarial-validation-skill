from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any


mapping_path = Path(sys.argv[1])
log_path = Path(sys.argv[2])
scenario = sys.argv[3] if len(sys.argv) > 3 else "success"
mapping: dict[str, Any] = json.loads(mapping_path.read_text(encoding="utf-8"))
thread_id = f"fake-{uuid.uuid4()}"
turn_id = f"turn-{uuid.uuid4()}"
thread_params: dict[str, Any] = {}
initialize_params: dict[str, Any] = {}


def emit(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, separators=(",", ":")), flush=True)


def log(value: dict[str, Any]) -> None:
    with log_path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")


def apply_writes(cwd: Path, specification: dict[str, Any]) -> None:
    for relative, content in specification.get("writes", {}).items():
        target = cwd / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, dict) and "base64" in content:
            target.write_bytes(base64.b64decode(content["base64"]))
        else:
            target.write_text(str(content), encoding="utf-8")
    for relative in specification.get("deletes", []):
        target = cwd / relative
        if target.exists():
            target.unlink()


for raw_line in sys.stdin:
    request = json.loads(raw_line)
    method = request.get("method")
    request_id = request.get("id")
    if method == "initialize":
        initialize_params = dict(request.get("params", {}))
        emit({"id": request_id, "result": {}})
    elif method == "initialized":
        continue
    elif method == "thread/start":
        thread_params = dict(request.get("params", {}))
        emit({"id": request_id, "result": {"thread": {"id": thread_id}}})
    elif method == "turn/start":
        role_input = json.loads(request["params"]["input"][0]["text"])
        role = role_input["role"]
        specification = mapping.get(role, mapping.get("default", {}))
        log(
            {
                "role": role,
                "thread_id": thread_id,
                "server_cwd": os.getcwd(),
                "initialize": initialize_params,
                "thread": thread_params,
                "turn": {
                    "model": request["params"].get("model"),
                    "effort": request["params"].get("effort"),
                },
                "input": role_input["input"],
                "output_schema": request["params"].get("outputSchema"),
            }
        )
        apply_writes(Path(thread_params["cwd"]), specification)
        emit({"id": request_id, "result": {"turn": {"id": turn_id}}})
        if scenario == "hang":
            while True:
                time.sleep(1)
        if scenario == "retryable_error":
            emit(
                {
                    "method": "error",
                    "params": {"error": {"message": "Reconnecting... 1/5"}},
                }
            )
        if scenario == "mcp_startup_status":
            emit(
                {
                    "method": "mcpServer/startupStatus/updated",
                    "params": {
                        "threadId": thread_id,
                        "name": "private-name-must-not-survive",
                        "status": "ready",
                    },
                }
            )
        event_thread = "wrong-thread" if scenario == "wrong_correlation" else thread_id
        report = specification.get("report", mapping.get("default_report", {}))
        emit(
            {
                "method": "item/completed",
                "params": {
                    "threadId": event_thread,
                    "turnId": turn_id,
                    "item": {
                        "type": "agentMessage",
                        "id": "final",
                        "phase": "final_answer",
                        "text": json.dumps(report, ensure_ascii=False, separators=(",", ":")),
                    },
                },
            }
        )
        if scenario == "success_with_survivor":
            survivor_path = Path(sys.argv[4])
            creation_flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
                subprocess, "CREATE_NEW_PROCESS_GROUP", 0
            )
            survivor = subprocess.Popen(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags,
            )
            survivor_path.write_text(str(survivor.pid), encoding="ascii")
        if scenario == "multiple_final":
            emit(
                {
                    "method": "item/completed",
                    "params": {
                        "threadId": thread_id,
                        "turnId": turn_id,
                        "item": {
                            "type": "agentMessage",
                            "id": "final-2",
                            "phase": "final_answer",
                            "text": json.dumps(report, separators=(",", ":")),
                        },
                    },
                }
            )
        emit(
            {
                "method": "turn/completed",
                "params": {
                    "threadId": thread_id,
                    "turn": {"id": turn_id, "status": "completed"},
                },
            }
        )
