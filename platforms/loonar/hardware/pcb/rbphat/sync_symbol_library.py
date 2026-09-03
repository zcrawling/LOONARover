#!/usr/bin/env python3
"""Synchronize the project library to the symbols embedded by SKiDL.

KiCad ERC compares each placed symbol against its external library copy. SKiDL
normalizes some symbol fields while embedding them, so this one-time/regen step
writes those exact normalized symbols back to ``rbphat.kicad_sym``.
"""

from copy import deepcopy
from pathlib import Path

from kiutils.schematic import Schematic
from kiutils.symbol import SymbolLib


ROOT = Path(__file__).resolve().parent
LIBRARY = ROOT / "rbphat.kicad_sym"


def main() -> None:
    by_name = {}
    version = "20230409"
    for schematic_path in [ROOT / "rbphat.kicad_sch"]:
        schematic = Schematic.from_file(str(schematic_path), encoding="utf-8")
        version = schematic.version
        for symbol in schematic.libSymbols:
            is_local = symbol.libraryNickname == "rbphat"
            is_power_flag_seed = symbol.libraryNickname == "power" and symbol.entryName == "PWR_FLAG"
            if not (is_local or is_power_flag_seed):
                continue
            symbol = deepcopy(symbol)
            symbol.libraryNickname = None
            by_name[symbol.entryName] = symbol
    symbols = list(by_name.values())
    if not symbols:
        raise RuntimeError("No rbphat symbols found in generated schematic")
    library = SymbolLib(
        version=version,
        generator="rbphat_sync",
        symbols=sorted(symbols, key=lambda item: item.entryName),
        filePath=str(LIBRARY),
    )
    LIBRARY.write_text(library.to_sexpr(), encoding="utf-8", newline="\n")
    print(f"Synchronized {len(symbols)} symbols to {LIBRARY}")


if __name__ == "__main__":
    main()
