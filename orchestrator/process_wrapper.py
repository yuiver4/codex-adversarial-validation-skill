from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    if len(values) < 3 or values[0] != "--gate" or "--" not in values[2:]:
        return 125
    separator = values.index("--", 2)
    gate = Path(values[1])
    command = values[separator + 1 :]
    if not command:
        return 125

    deadline = time.monotonic() + 30.0
    while not gate.exists():
        if time.monotonic() >= deadline:
            return 125
        time.sleep(0.01)
    try:
        gate.unlink()
    except OSError:
        return 125

    child = subprocess.Popen(
        command,
        stdin=sys.stdin.buffer,
        stdout=sys.stdout.buffer,
        stderr=sys.stderr.buffer,
    )
    return child.wait()


if __name__ == "__main__":
    raise SystemExit(main())
