#!/usr/bin/env python3
"""Apply KiCad instance flags that SKiDL 2.3.0 does not emit correctly."""

from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parent
DNP_REFS = {"R105", "R106", "R205", "R206"}


def _symbol_blocks(text: str):
    """Yield balanced top-level symbol-instance spans from a schematic."""
    for match in re.finditer(r"(?m)^  \(symbol(?:\s|$)", text):
        start = match.start()
        depth = 0
        quoted = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if quoted:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    quoted = False
                continue
            if char == '"':
                quoted = True
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    yield start, index + 1
                    break
        else:
            raise ValueError(f"Unbalanced symbol expression at byte {start}")


def mark_dnp_file(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    replacements: list[tuple[int, int, str]] = []
    found: set[str] = set()
    for start, end in _symbol_blocks(text):
        block = text[start:end]
        reference = re.search(r'\(property\s+"Reference"\s+"([^"]+)"', block)
        if reference is None or reference.group(1) not in DNP_REFS:
            continue
        ref = reference.group(1)
        updated, count = re.subn(r"\(dnp\s+no\)", "(dnp yes)", block, count=1)
        if count == 0 and "(dnp yes)" not in block:
            raise ValueError(f"{path.name}: no dnp flag found in {ref}")
        replacements.append((start, end, updated))
        found.add(ref)

    for start, end, block in reversed(replacements):
        text = text[:start] + block + text[end:]
    if replacements:
        path.write_text(text, encoding="utf-8", newline="")
    return found


def mark_dnp_files() -> None:
    # The final design is deliberately a single-sheet schematic.
    found = mark_dnp_file(ROOT / "rbphat.kicad_sch")
    if found != DNP_REFS:
        missing = ", ".join(sorted(DNP_REFS - found)) or "none"
        raise RuntimeError(f"DNP flag audit failed; missing: {missing}")
    print(f"Marked DNP: {', '.join(sorted(found))}")


if __name__ == "__main__":
    mark_dnp_files()
