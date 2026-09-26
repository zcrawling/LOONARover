"""Select the MCU role and physical board. No release metadata is generated."""

import os
from pathlib import Path
import platform

Import("env")

# Ubuntu's generic ARM toolchain lacks the newlib locking ABI required by
# this FreeRTOS port. Build on the development PC and upload through Pi SSH.
if platform.system() == "Linux" and platform.machine() in ("aarch64", "arm64", "armv7l"):
    raise RuntimeError("Build on the development PC using tools/remote-flash-control.py; Pi only uploads.")

uid = int(os.environ.get("LOONAR_BOARD_UID", "0"), 16)
if not 0 <= uid <= 0xFFFFFFFFFFFFFFFF:
    raise ValueError("LOONAR_BOARD_UID must be a 64-bit hexadecimal UID")
# Only runtime.cpp depends on board identity; changing UID must not rebuild
# the whole Arduino core and every library during the two-stage first upload.
role = 2 if env["PIOENV"].startswith("payload") else 1
directory = Path(env.subst("$BUILD_DIR"))
directory.mkdir(parents=True, exist_ok=True)
header = directory / "loonar_board_config.h"
content = (f"#pragma once\n#define LOONAR_MCU_ROLE {role}\n"
           f"#define LOONAR_EXPECTED_UID 0x{uid:016x}ULL\n")
if not header.exists() or header.read_text() != content:
    header.write_text(content)
env.Append(CPPPATH=[str(directory)])
