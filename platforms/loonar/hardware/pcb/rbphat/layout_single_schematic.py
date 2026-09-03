#!/usr/bin/env python3
"""Arrange the flattened RBPHAT circuit as one readable A3 schematic."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import uuid
import xml.etree.ElementTree as ET

from kiutils.items.common import Effects, Font, Justify, Position
from kiutils.items.schitems import LocalLabel, Text
from kiutils.schematic import Schematic


ROOT = Path(__file__).resolve().parent
SCHEMATIC = ROOT / "rbphat.kicad_sch"
NETLIST = ROOT / "rbphat.xml"


# Component centers in millimetres on an A3 landscape sheet.  Angles are kept
# from the generated symbols so every attached pin label remains valid after a
# pure translation.
TARGET = {
    # Raspberry Pi interface.
    "J1": (48.0, 140.0), "TP1": (34.0, 60.0), "TP2": (62.0, 60.0),
    # UART2 / control RS-422, upper signal row.
    "R101": (83.0, 88.0), "U2": (108.0, 88.0),
    "R102": (132.0, 76.0), "R103": (132.0, 101.0),
    "R100": (154.0, 50.0), "C100": (176.0, 50.0), "TP101": (202.0, 50.0),
    "U1": (166.0, 88.0), "D101": (207.0, 76.0), "D102": (207.0, 101.0),
    "R105": (232.0, 72.0), "R104": (232.0, 88.0), "R106": (232.0, 105.0),
    "J2": (264.0, 88.0),
    # UART4 / payload RS-422, lower signal row.
    "R201": (83.0, 174.0), "U4": (108.0, 174.0),
    "R202": (132.0, 162.0), "R203": (132.0, 187.0),
    "R200": (154.0, 136.0), "C200": (176.0, 136.0), "TP201": (202.0, 136.0),
    "U3": (166.0, 174.0), "D201": (207.0, 162.0), "D202": (207.0, 187.0),
    "R205": (232.0, 158.0), "R204": (232.0, 174.0), "R206": (232.0, 191.0),
    "J3": (264.0, 174.0),
    # Battery divider, powered-off isolation and ADC.
    "C300": (328.0, 126.0), "U5": (328.0, 158.0),
    "C301": (376.0, 126.0), "U6": (376.0, 158.0),
    "J4": (296.0, 216.0), "R301": (315.0, 207.0), "R302": (337.0, 207.0),
    "R303": (354.0, 232.0), "C302": (380.0, 232.0),
    "TP301": (298.0, 259.0), "TP302": (330.0, 259.0),
    "TP303": (362.0, 259.0), "TP304": (394.0, 259.0),
    # ERC power flags, kept visible but out of the signal flow.
    "#FLG0101": (30.0, 27.0), "#FLG0102": (55.0, 27.0),
    "#FLG0103": (160.0, 27.0), "#FLG0104": (160.0, 119.0),
}

FLAG_NETS = {
    "#FLG0101": "+3V3_PI",
    "#FLG0102": "GND",
    "#FLG0103": "MAX1_VCC",
    "#FLG0104": "MAX2_VCC",
}


def reference(symbol) -> str:
    return next((item.value for item in symbol.properties if item.key == "Reference"), "")


def move_position(position: Position, dx: float, dy: float) -> None:
    position.X = round(position.X + dx, 3)
    position.Y = round(position.Y + dy, 3)


def move_symbol(symbol, dx: float, dy: float) -> None:
    move_position(symbol.position, dx, dy)
    for prop in symbol.properties:
        move_position(prop.position, dx, dy)


def clean_symbol_properties(symbol) -> None:
    """Show review-useful fields only; generated URLs/footprints are metadata."""
    ref = reference(symbol)
    for prop in symbol.properties:
        if prop.key not in {"Reference", "Value"}:
            prop.effects.hide = True
            continue
        prop.effects.hide = ref.startswith("#FLG") and prop.key == "Reference"
        prop.effects.font.height = 0.95
        prop.effects.font.width = 0.95
        prop.effects.justify.horizontally = None
        prop.position.angle = 0


def load_pin_nets() -> dict[tuple[str, str], str]:
    if not NETLIST.exists():
        raise FileNotFoundError(f"Generate {NETLIST.name} before arranging the schematic")
    root = ET.parse(NETLIST).getroot()
    result: dict[tuple[str, str], str] = {}
    for net in root.findall("./nets/net"):
        # KiCad prefixes root-sheet local labels with "/" in exported XML.
        name = net.attrib["name"].removeprefix("/")
        for node in net.findall("node"):
            result[(node.attrib["ref"], node.attrib["pin"])] = name
    return result


def pin_world(symbol, pin) -> tuple[float, float]:
    """Return a KiCad library pin connection point in sheet coordinates."""
    x, y = pin.position.X, pin.position.Y
    if symbol.mirror == "x":
        y = -y
    elif symbol.mirror == "y":
        x = -x

    angle = int(round(symbol.position.angle or 0)) % 360
    # KiCad symbol-library Y points up while sheet coordinates point down.
    if angle == 0:
        dx, dy = x, -y
    elif angle == 90:
        dx, dy = -y, -x
    elif angle == 180:
        dx, dy = -x, y
    elif angle == 270:
        dx, dy = y, x
    else:
        raise ValueError(f"Unsupported symbol angle {angle} for {reference(symbol)}")
    return symbol.position.X + dx, symbol.position.Y + dy


def layout_single_schematic() -> None:
    schematic = Schematic.from_file(str(SCHEMATIC), encoding="utf-8")
    schematic.paper.paperSize = "A3"
    schematic.paper.portrait = False

    anchors = {
        reference(symbol): symbol
        for symbol in schematic.schematicSymbols
        if reference(symbol) in TARGET
    }
    missing = set(TARGET) - set(anchors)
    if missing:
        raise RuntimeError(f"Single-sheet layout missing symbols: {', '.join(sorted(missing))}")

    # Only whole 2.54 mm translations are allowed. This preserves the original
    # electrical grid phase of every pin even when symbol centres differ.
    deltas = {
        ref: (
            round((TARGET[ref][0] - symbol.position.X) / 2.54) * 2.54,
            round((TARGET[ref][1] - symbol.position.Y) / 2.54) * 2.54,
        )
        for ref, symbol in anchors.items()
    }
    pin_nets = load_pin_nets()
    library = {item.entryName: item for item in schematic.libSymbols}
    no_connect_template = deepcopy(schematic.noConnects[0])

    # Move the 44 real parts and four explicit ERC flags.
    for ref, symbol in anchors.items():
        move_symbol(symbol, *deltas[ref])
        clean_symbol_properties(symbol)

    # The generated sheet intentionally overlaps some same-net endpoints. Once
    # the parts are spread out, moving only the original shared label would
    # disconnect the other pins. Rebuild one explicit endpoint marker per pin
    # from the exported pin/net table instead. This is deterministic and makes
    # the final connectivity independent of the auto-router's overlap choices.
    labels = []
    no_connects = []
    for ref, symbol in anchors.items():
        units = [unit for unit in library[symbol.entryName].units if unit.unitId == symbol.unit]
        if len(units) != 1:
            raise RuntimeError(f"{ref}: cannot resolve library unit {symbol.unit}")
        for pin in units[0].pins:
            number = str(pin.number)
            net = FLAG_NETS.get(ref) if ref.startswith("#FLG") else pin_nets.get((ref, number))
            if net is None:
                raise RuntimeError(f"{ref}.{number}: no net assignment in {NETLIST.name}")
            x, y = pin_world(symbol, pin)
            if net.startswith("unconnected-"):
                marker = deepcopy(no_connect_template)
                marker.position = Position(round(x, 3), round(y, 3))
                marker.uuid = str(uuid.uuid4())
                no_connects.append(marker)
                continue

            angle = (int(round(pin.position.angle or 0)) - int(round(symbol.position.angle or 0))) % 360
            label = LocalLabel(
                net,
                Position(round(x, 3), round(y, 3), angle),
                Effects(
                    font=Font(height=0.9, width=0.9, thickness=0.13),
                    justify=Justify(horizontally="left" if angle in (0, 90) else "right"),
                ),
                str(uuid.uuid4()),
            )
            labels.append(label)

    schematic.labels = labels
    schematic.globalLabels = []
    schematic.noConnects = no_connects
    schematic.junctions = []
    schematic.graphicalItems = []
    schematic.schematicSymbols = [
        symbol for symbol in schematic.schematicSymbols
        if not reference(symbol).startswith("#PWR")
    ]

    schematic.texts = [
        Text("RASPBERRY PI 40-PIN", Position(24.0, 42.0, 0), Effects(font=Font(height=2.0, width=2.0, thickness=0.35, bold=True)), str(uuid.uuid4())),
        Text("UART2 / CONTROL RS-422", Position(78.0, 38.0, 0), Effects(font=Font(height=2.0, width=2.0, thickness=0.35, bold=True)), str(uuid.uuid4())),
        Text("UART4 / PAYLOAD RS-422", Position(78.0, 124.0, 0), Effects(font=Font(height=2.0, width=2.0, thickness=0.35, bold=True)), str(uuid.uuid4())),
        Text("3S BATTERY SENSE / POWER-OFF ISOLATION", Position(287.0, 105.0, 0), Effects(font=Font(height=2.0, width=2.0, thickness=0.35, bold=True)), str(uuid.uuid4())),
        Text("R105/R106/R205/R206: DNP", Position(286.0, 70.0, 0), Effects(font=Font(height=1.4, width=1.4, thickness=0.25, bold=True)), str(uuid.uuid4())),
        Text("MAX3490E: 1 VCC, 2 RO, 3 DI, 4 GND, 5 Y, 6 Z, 7 B, 8 A", Position(78.0, 222.0, 0), Effects(font=Font(height=1.4, width=1.4, thickness=0.25)), str(uuid.uuid4())),
        Text("12.6V -> 2.025V; VBAT = VADC x 6.222222", Position(286.0, 276.0, 0), Effects(font=Font(height=1.4, width=1.4, thickness=0.25)), str(uuid.uuid4())),
    ]

    # Force LF even when the generator runs under Windows so repository diffs
    # do not report every KiCad line as trailing whitespace.
    SCHEMATIC.write_text(schematic.to_sexpr(), encoding="utf-8", newline="\n")
    print(f"Laid out {len(anchors)} symbols on one A3 sheet")


if __name__ == "__main__":
    layout_single_schematic()
