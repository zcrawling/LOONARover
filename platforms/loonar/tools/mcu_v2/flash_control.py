"""Build and upload Control USB firmware to one explicitly selected TyTools board."""

import argparse
import json
import os
import platform
from pathlib import Path
import shutil
import struct
import subprocess
import time

import serial
from .config import CONTROL_GEOMETRY
from .wire import Frame, Kind, Parser


def board_info(tag):
    boards = json.loads(subprocess.check_output(
        ["tycmd", "list", "--verbose", "--output", "json"], text=True
    ))
    matches = [board for board in boards if board["tag"] == tag]
    if len(matches) != 1:
        raise ValueError("Copy the exact Control tag from tycmd list (for example, 19971280-Teensy)")
    board = matches[0]
    if board["model"] not in ("Teensy", "Teensy 4.1"):
        raise ValueError(f"Expected Teensy 4.1, found {board['model']}")
    return board


def serial_path(board):
    ports = [path for _, path in board.get("interfaces", []) if path.startswith("/dev/ttyACM")]
    if len(ports) != 1:
        return None
    for path in sorted(Path("/dev/serial/by-id").glob("*")):
        if path.resolve() == Path(ports[0]).resolve():
            return str(path)
    return None


def hello(device):
    if device is None:
        return None
    with serial.Serial(device, 2000000, timeout=0.05, write_timeout=0.2, exclusive=True) as port:
        parser = Parser()
        # Detect an existing Payload image as well as Control; never replace it.
        for role in (1, 2):
            port.write(Frame(role, Kind.HELLO_REQUEST, sequence=1).encode())
        end = time.monotonic() + 2
        while time.monotonic() < end:
            for frame in parser.feed(port.read(4096)):
                if frame.kind != Kind.HELLO or len(frame.payload) != 28:
                    continue
                if frame.role != 1:
                    raise ValueError("Selected board runs Payload firmware; refusing Control upload")
                uid, expected, _, _, flags = struct.unpack("<QQIII", frame.payload)
                return uid, expected, bool(flags & 1)
    return None


def wait_hello(tag):
    end = time.monotonic() + 15
    while time.monotonic() < end:
        # The selected board may briefly disappear during USB re-enumeration.
        try:
            board = board_info(tag)
        except ValueError:
            time.sleep(0.25)
            continue
        device = serial_path(board)
        if device:
            result = hello(device)
            if result:
                return device, result
        time.sleep(0.25)
    raise TimeoutError("Upload finished but selected Control did not return a LNR2 HELLO")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--board", required=True, help="Complete Control tag from tycmd list")
    parser.add_argument("--registry", type=Path, required=True, help="Control connection settings to write")
    parser.add_argument("--external-build", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not args.board.strip() or args.board.startswith("@"):
        parser.error("--board must be the exact Control tag from tycmd list, including its serial number")
    registry = args.registry.expanduser()
    config = json.loads(registry.read_text()) if registry.exists() else {"schema": 2, "devices": {}}
    if config.get("schema") != 2 or not isinstance(config.get("devices"), dict):
        raise ValueError("Registry must use schema 2")
    old = config["devices"].get("control", {})
    for role, entry in config["devices"].items():
        if role != "control" and entry.get("upload_board") == args.board:
            raise ValueError("This USB board is already assigned to another role")
    if old.get("upload_board") and old["upload_board"] != args.board:
        raise ValueError("This registry belongs to another Control USB board")
    if subprocess.run(["systemctl", "is-active", "--quiet", "loonar-mcu@control.service"]).returncode == 0:
        raise ValueError("Stop loonar-mcu@control.service and the motor bench before uploading")
    pio = shutil.which("pio") or str(Path.home() / ".local/bin/pio")
    if not args.external_build and platform.system() == "Linux" and platform.machine() in ("aarch64", "arm64", "armv7l"):
        raise ValueError("Run tools/remote-flash-control.py on the development PC; Pi only uploads.")
    if not args.external_build and not Path(pio).is_file():
        raise ValueError("PlatformIO missing: install it as described in motor_usb_bench.md")
    firmware = Path(__file__).resolve().parents[2] / "firmware/control"
    info = board_info(args.board)
    device = serial_path(info)
    result = hello(device)
    if result and old.get("uid") and int(old["uid"], 16) != result[0]:
        raise ValueError("Selected MCU UID differs from the existing Control registry")
    # On the first install, a physical USB tag is the user's role assignment.
    # With no LNR2 reply, a discovery-only image reads the actual silicon UID.
    def build_upload(uid):
        if args.external_build:
            # SSH parent builds on the PC, copies the HEX, then returns its Pi path.
            print("LOONAR_BUILD_REQUEST " + f"{uid:016x}", flush=True)
            try:
                image = Path(input()).expanduser()
            except EOFError:
                raise ValueError("PC build/transfer interrupted; no new HEX will be uploaded") from None
            if not image.is_file():
                raise ValueError("PC did not supply a firmware HEX file")
        else:
            environment = dict(os.environ, LOONAR_BOARD_UID=f"{uid:016x}")
            subprocess.run([pio, "run", "-d", str(firmware), "-e", "teensy41_usb"],
                           env=environment, check=True)
            image = firmware / ".pio/build/teensy41_usb/firmware.hex"
        board_info(args.board)  # Target must still exist; never choose the first board.
        subprocess.run(["tycmd", "upload", "--board", args.board, str(image)], check=True)
        return wait_hello(args.board)

    if result is None:
        if old.get("uid"):
            if old.get("upload_board") != args.board:
                raise ValueError("Nonresponding MCU has no matching stored USB tag")
            # A known Control may already be in the bootloader after an interrupted upload.
            uid = int(old["uid"], 16)
        else:
            print("Installing discovery-only Control image on", args.board, flush=True)
            device, result = build_upload(0)
            uid = result[0]
    else:
        uid = result[0]
    if not uid:
        raise ValueError("MCU returned a zero UID")
    for role, entry in config["devices"].items():
        if role != "control" and int(entry["uid"], 16) == uid:
            raise ValueError("This UID is already registered to another role")
    print(f"Building Control for UID={uid:016x}; M1=right, M2=left", flush=True)
    device, result = build_upload(uid)
    if result != (uid, uid, True):
        raise ValueError("Post-upload Control UID/binding does not match")
    config["devices"]["control"] = {
        **old, "uid": f"{uid:016x}", "device": device, "transport": "usb",
        "upload_board": args.board,
        "roboclaw": old.get("roboclaw", {"address": 128, "baud": 115200}),
        "geometry": dict(CONTROL_GEOMETRY),
    }
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(json.dumps(config, indent=2) + "\n")
    print(f"Control upload and HELLO succeeded. Registry: {registry}\nDevice: {device}")
    print("No motion commands were sent. Applied confirmed Control geometry:", CONTROL_GEOMETRY)


if __name__ == "__main__":
    try:
        main()
    except (EOFError, OSError, ValueError, TimeoutError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error)) from error
