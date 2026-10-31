"""Run a repair command and save its complete output and exit status."""

from __future__ import annotations

import argparse
import datetime
import shlex
import subprocess
from pathlib import Path


def main() -> None:
    """Capture one command without hiding a failed exit status."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("a command is required after the output path")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as evidence:
        header = (
            f"UTC: {datetime.datetime.now(datetime.timezone.utc).isoformat()}\n"
            f"CWD: {Path.cwd()}\nCOMMAND: {shlex.join(command)}\n\n"
        )
        evidence.write(header)
        evidence.flush()
        print(header, end="", flush=True)
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        try:
            for line in process.stdout:
                evidence.write(line)
                evidence.flush()
                print(line, end="", flush=True)
            status = process.wait()
        except KeyboardInterrupt:
            process.terminate()
            status = process.wait()
        footer = f"\nEXIT_STATUS: {status}\n"
        evidence.write(footer)
        print(footer, end="", flush=True)
    raise SystemExit(status)


if __name__ == "__main__":
    main()
