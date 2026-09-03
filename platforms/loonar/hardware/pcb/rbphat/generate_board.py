#!/usr/bin/env python3
"""Generate RBPHAT Rev.A's 4-layer KiCad PCB from the native schematic netlist.

The script uses KiCad's bundled ``pcbnew`` Python module. It preserves the
schematic sheet/symbol UUID path on every footprint so KiCad can check schematic
parity without GUI-based "Update PCB from Schematic".
"""

from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

import pcbnew


ROOT = Path(__file__).resolve().parent
SCHEMATIC = ROOT / "rbphat.kicad_sch"
NETLIST = ROOT / "rbphat.xml"
OUTPUT = ROOT / "rbphat.kicad_pcb"
TEMPLATE = Path("/usr/share/kicad/template/RaspberryPi-HAT/RaspberryPi-HAT.kicad_pcb")
FOOTPRINT_ROOT = Path("/usr/share/kicad/footprints")


# Positions are in the official Raspberry Pi HAT template coordinate system.
# The outline spans approximately X=100..165 mm, Y=44..100 mm.
PLACEMENT = {
    "J1": (108.37, 48.77, 0),
    # UART2 / Control link.
    "R101": (121.5, 57.0, 0),
    "U2": (128.0, 60.0, 0),
    "R102": (133.0, 57.0, 0),
    "R103": (133.0, 63.0, 0),
    "R100": (138.0, 52.5, 0),
    "C100": (143.0, 52.5, 0),
    "U1": (143.0, 60.0, 0),
    "TP101": (149.0, 52.5, 0),
    "R105": (149.0, 64.0, 0),
    "R104": (149.0, 67.0, 0),
    "R106": (149.0, 70.0, 0),
    "D101": (155.0, 57.0, 90),
    "D102": (155.0, 65.0, 90),
    "J2": (162.0, 61.0, 90),
    # UART4 / Payload link.
    "R201": (121.5, 76.0, 0),
    "U4": (128.0, 79.0, 0),
    "R202": (133.0, 76.0, 0),
    "R203": (133.0, 82.0, 0),
    "R200": (138.0, 72.0, 0),
    "C200": (143.0, 72.0, 0),
    "U3": (143.0, 79.0, 0),
    "TP201": (149.0, 73.0, 0),
    "R205": (149.0, 82.0, 0),
    "R204": (149.0, 85.0, 0),
    "R206": (149.0, 88.0, 0),
    "D201": (155.0, 77.0, 90),
    "D202": (155.0, 85.0, 90),
    "J3": (162.0, 81.0, 90),
    # Battery sense / ADC, kept away from the differential blocks.
    "J4": (102.0, 87.0, 270),
    "R301": (108.0, 86.0, 0),
    "R302": (113.0, 86.0, 0),
    "R303": (117.0, 91.0, 90),
    "C302": (121.0, 94.0, 0),
    "U5": (127.0, 88.0, 0),
    "C300": (127.0, 82.0, 0),
    "U6": (136.0, 88.0, 0),
    "C301": (136.0, 82.0, 0),
    "TP301": (108.0, 94.0, 0),
    "TP302": (116.0, 96.0, 0),
    "TP303": (128.0, 96.0, 0),
    "TP304": (138.0, 95.0, 0),
    "TP1": (113.0, 55.0, 0),
    "TP2": (117.0, 55.0, 0),
}


def mm(value: float) -> int:
    return pcbnew.FromMM(value)


def point(x: float, y: float) -> pcbnew.VECTOR2I:
    return pcbnew.VECTOR2I(mm(x), mm(y))


def export_xml_netlist() -> None:
    subprocess.run(
        [
            "kicad-cli",
            "sch",
            "export",
            "netlist",
            "--format",
            "kicadxml",
            "-o",
            str(NETLIST),
            str(SCHEMATIC),
        ],
        check=True,
    )


def load_footprint(identifier: str) -> pcbnew.FOOTPRINT:
    library, name = identifier.split(":", 1)
    plugin = pcbnew.PCB_IO_KICAD_SEXPR()
    footprint = plugin.FootprintLoad(str(FOOTPRINT_ROOT / f"{library}.pretty"), name)
    if footprint is None:
        raise FileNotFoundError(f"Unable to load footprint {identifier}")
    return footprint


def prepare_hat_template() -> pcbnew.BOARD:
    board = pcbnew.LoadBoard(str(TEMPLATE))
    # The official template supplies the HAT edge profile and M2.5 holes. Its
    # example header is replaced by the schematic-linked J1 footprint.
    for footprint in list(board.GetFootprints()):
        if footprint.GetReference() == "J1":
            board.Remove(footprint)
        else:
            footprint.SetBoardOnly(True)
            footprint.SetExcludedFromBOM(True)
    for track in list(board.GetTracks()):
        board.Remove(track)
    for zone in list(board.Zones()):
        board.Remove(zone)
    for drawing in list(board.GetDrawings()):
        if drawing.GetLayer() != pcbnew.Edge_Cuts:
            board.Remove(drawing)

    board.SetCopperLayerCount(4)
    board.SetLayerName(pcbnew.In1_Cu, "GND")
    board.SetLayerName(pcbnew.In2_Cu, "PWR")
    return board


def add_silkscreen(board: pcbnew.BOARD, text: str, x: float, y: float, size: float = 1.0) -> None:
    item = pcbnew.PCB_TEXT(board)
    item.SetText(text)
    item.SetLayer(pcbnew.F_SilkS)
    item.SetPosition(point(x, y))
    item.SetTextSize(point(size, size))
    item.SetTextThickness(mm(0.15))
    board.Add(item)


def build_board() -> pcbnew.BOARD:
    export_xml_netlist()
    root = ET.parse(NETLIST).getroot()
    components = list(root.findall("./components/comp"))
    # KiCad 9's deprecated SWIG binding can lose its footprint-plugin type
    # wrapper after items are removed from a loaded board. Load every schematic
    # footprint first, then prepare the template board.
    loaded_footprints: dict[str, pcbnew.FOOTPRINT] = {}
    for component in components:
        ref = component.attrib["ref"]
        footprint_id = component.findtext("footprint", default="")
        if footprint_id and footprint_id != ":":
            loaded_footprints[ref] = load_footprint(footprint_id)
    board = prepare_hat_template()

    net_items: dict[str, pcbnew.NETINFO_ITEM] = {}
    pin_nets: dict[tuple[str, str], str] = {}
    for net_element in root.findall("./nets/net"):
        name = net_element.attrib["name"]
        net_item = pcbnew.NETINFO_ITEM(board, name)
        board.Add(net_item)
        net_items[name] = net_item
        for node in net_element.findall("node"):
            pin_nets[(node.attrib["ref"], node.attrib["pin"])] = name

    missing_positions = []
    for component in components:
        ref = component.attrib["ref"]
        footprint_id = component.findtext("footprint", default="")
        if not footprint_id or footprint_id == ":":
            continue
        if ref not in PLACEMENT:
            missing_positions.append(ref)
            continue
        footprint = loaded_footprints[ref]
        footprint.SetReference(ref)
        footprint.SetValue(component.findtext("value", default=""))
        footprint.SetSheetfile(
            next(
                (p.attrib["value"] for p in component.findall("property") if p.attrib.get("name") == "Sheetfile"),
                "rbphat.kicad_sch",
            )
        )
        sheetpath = component.find("sheetpath")
        sheet_name = sheetpath.attrib.get("names", "/") if sheetpath is not None else "/"
        sheet_uuid = sheetpath.attrib.get("tstamps", "/") if sheetpath is not None else "/"
        footprint.SetSheetname(sheet_name.strip("/"))
        symbol_uuid = component.findtext("tstamps", default="")
        full_path = f"{sheet_uuid.rstrip('/')}/{symbol_uuid}"
        footprint.SetPath(pcbnew.KIID_PATH(full_path))
        if ref in {"R105", "R106", "R205", "R206"}:
            footprint.SetDNP(True)
        x, y, angle = PLACEMENT[ref]
        footprint.SetPosition(point(x, y))
        footprint.SetOrientationDegrees(angle)
        # Avoid Footprint.Value()/Reference() here. KiCad 9's deprecated SWIG
        # binding sometimes returns those fields as an untyped SwigPyObject
        # after another board has been loaded. The library defaults already
        # hide values and show references, so no design information is lost.
        board.Add(footprint)
        for pad in footprint.Pads():
            net_name = pin_nets.get((ref, pad.GetNumber()))
            if net_name:
                pad.SetNet(net_items[net_name])

    if missing_positions:
        raise RuntimeError(f"Missing placement coordinates: {', '.join(sorted(missing_positions))}")

    add_silkscreen(board, "RBPHAT REV.A", 107.0, 72.0, 1.2)
    add_silkscreen(board, "CTRL RS-422", 153.0, 52.0, 0.8)
    add_silkscreen(board, "PAYLOAD RS-422", 151.0, 92.0, 0.8)
    add_silkscreen(board, "BAT SENSE", 103.0, 82.0, 0.8)
    add_silkscreen(board, "REMOVE R100/R200 FOR I-METER", 112.0, 98.5, 0.65)
    add_silkscreen(board, "DO NOT TIE +RAILS", 107.0, 75.0, 0.75)

    board.BuildListOfNets()
    pcbnew.SaveBoard(str(OUTPUT), board)
    return board


if __name__ == "__main__":
    result = build_board()
    print(
        f"Wrote {OUTPUT}: {len(list(result.GetFootprints()))} footprints, "
        f"{result.GetNetCount()} nets, {result.GetCopperLayerCount()} copper layers"
    )
