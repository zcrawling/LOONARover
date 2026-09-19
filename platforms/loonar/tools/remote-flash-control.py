#!/usr/bin/env python3
"""Build on this PC and upload Control via the Pi's USB port over SSH."""

import argparse
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, help="Pi SSH address, e.g. loonar@192.168.0.99")
    parser.add_argument("--board", required=True, help="Exact Control tag from tycmd list")
    args = parser.parse_args()
    if args.host.startswith("-") or any(c.isspace() for c in args.host):
        parser.error("--host must be a single SSH destination")
    if platform.system() == "Linux" and platform.machine() != "x86_64":
        parser.error("Run this command on the development PC, not the Pi")
    pio = shutil.which("pio") or str(Path.home() / ".local/bin/pio")
    if not Path(pio).is_file():
        parser.error("PlatformIO is not installed on this PC")
    tools = Path(__file__).resolve().parent
    firmware = tools.parent / "firmware/control"
    image = firmware / ".pio/build/teensy41_usb/firmware.hex"

    def build(uid):
        subprocess.run([pio, "run", "-d", str(firmware), "-e", "teensy41_usb"],
                       env=dict(os.environ, LOONAR_BOARD_UID=uid), check=True)

    with tempfile.TemporaryDirectory(prefix="loonar-ssh-") as local:
        control = str(Path(local) / "ssh")
        ssh = ["ssh", "-S", control, args.host]
        scp = ["scp", "-o", f"ControlPath={control}"]
        remote = None
        child = None
        try:
            # One password prompt, shared by commands and file transfers.
            subprocess.run(["ssh", "-M", "-S", control, "-o", "ControlPersist=60",
                            "-fnNT", args.host], check=True)
            candidate = subprocess.check_output(
                ssh + ["mktemp -d /tmp/loonar-upload.XXXXXXXX"], text=True).strip()
            if not re.fullmatch(r"/tmp/loonar-upload\.[A-Za-z0-9]{8}", candidate):
                raise ValueError("Unexpected remote upload directory")
            remote = candidate
            subprocess.run(scp + ["-r", str(tools / "mcu_v2"), f"{args.host}:{remote}/"], check=True)
            command = (
                'export PATH="$HOME/.local/bin:$PATH"; '
                f"export PYTHONPATH={shlex.quote(remote)}; "
                "python3 -u -m mcu_v2.flash_control --external-build "
                f"--board {shlex.quote(args.board)} "
                '--registry "$HOME/loonar-motor-bench/control.json"'
            )
            child = subprocess.Popen(ssh + [command], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, text=True, bufsize=1)
            for line in child.stdout:
                if not line.startswith("LOONAR_BUILD_REQUEST "):
                    print(line, end="", flush=True)
                    continue
                uid = line.removeprefix("LOONAR_BUILD_REQUEST ").strip()
                if len(uid) != 16 or any(c not in "0123456789abcdef" for c in uid):
                    raise ValueError("Invalid MCU UID in build request")
                build(uid)
                subprocess.run(scp + [str(image), f"{args.host}:{remote}/control.hex"], check=True)
                child.stdin.write(f"{remote}/control.hex\n")
                child.stdin.flush()
            if child.wait() != 0:
                raise RuntimeError("Pi upload failed; see the preceding error")
        finally:
            # Closing input cancels a Pi process waiting for a failed/cancelled build.
            if child is not None and child.poll() is None:
                try:
                    child.stdin.close()
                except BrokenPipeError:
                    pass
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.terminate()
                    child.wait()
            if remote:
                subprocess.run(ssh + ["rm -rf -- " + shlex.quote(remote)], check=False)
            subprocess.run(["ssh", "-S", control, "-O", "exit", args.host],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit("Upload interrupted") from None
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error)) from error
