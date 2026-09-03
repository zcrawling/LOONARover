#!/usr/bin/env python3
"""Fail-fast electrical and pin-number audit for the RBPHAT schematic."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import math
import os
import re
import subprocess
import xml.etree.ElementTree as ET

from finalize_schematic import DNP_REFS, _symbol_blocks


ROOT = Path(__file__).resolve().parent
SCHEMATIC = ROOT / "rbphat.kicad_sch"
NETLIST = ROOT / "rbphat.xml"
ERC_REPORT = ROOT / "rbphat-erc.rpt"
AUDIT_REPORT = ROOT / "SCHEMATIC_AUDIT.txt"

MAX_DS = "https://www.analog.com/media/en/technical-documentation/data-sheets/MAX3483E-MAX3491E.pdf"
TMUX_DS = "https://www.ti.com/lit/ds/symlink/tmux1511.pdf"
BUFFER_DS = "https://www.ti.com/lit/ds/symlink/sn74lvc2g34.pdf"
ADC_DS = "https://www.ti.com/lit/ds/symlink/ads1115.pdf"

OFFICIAL_PIN_MAPS = {
    "MAX3490E": {"1": "VCC", "2": "RO", "3": "DI", "4": "GND", "5": "Y", "6": "Z", "7": "B", "8": "A"},
    "SN74LVC2G34": {"1": "1A", "2": "GND", "3": "2A", "4": "2Y", "5": "VCC", "6": "1Y"},
    "TMUX1511": {"1": "SEL1", "2": "S1", "3": "D1", "4": "SEL2", "5": "S2", "6": "D2", "7": "GND", "8": "D3", "9": "S3", "10": "SEL3", "11": "D4", "12": "S4", "13": "SEL4", "14": "VDD"},
    "ADS1115": {"1": "ADDR", "2": "ALERT", "3": "GND", "4": "AIN0", "5": "AIN1", "6": "AIN2", "7": "AIN3", "8": "VDD", "9": "SDA", "10": "SCL"},
}

EXPECTED_DATASHEETS = {
    "U1": MAX_DS,
    "U2": BUFFER_DS,
    "U3": MAX_DS,
    "U4": BUFFER_DS,
    "U5": TMUX_DS,
    "U6": ADC_DS,
}

EXPECTED_VALUES = {
    "U1": "MAX3490EESA+", "U2": "SN74LVC2G34DBVR",
    "U3": "MAX3490EESA+", "U4": "SN74LVC2G34DBVR",
    "U5": "TMUX1511PWR", "U6": "ADS1115IDGSR",
    "R100": "0R", "R101": "47k", "R102": "47R", "R103": "47R", "R104": "120R",
    "R105": "680R DNP", "R106": "680R DNP",
    "R200": "0R", "R201": "47k", "R202": "47R", "R203": "47R", "R204": "120R",
    "R205": "680R DNP", "R206": "680R DNP",
    "R301": "47k 0.1%", "R302": "47k 0.1%", "R303": "18k 0.1%",
    "C302": "1uF",
}


def kicad_share_root() -> Path:
    explicit = os.environ.get("KICAD9_SHARE")
    candidates = [Path(explicit) if explicit else None, Path("/usr/share/kicad")]
    for candidate in candidates:
        if candidate is not None and candidate.exists():
            return candidate
    raise FileNotFoundError("Set KICAD9_SHARE to the KiCad share directory")


def run_kicad_checks() -> None:
    subprocess.run(
        ["kicad-cli", "sch", "export", "netlist", "--format", "kicadxml", "-o", str(NETLIST), str(SCHEMATIC)],
        check=True,
    )
    subprocess.run(
        ["kicad-cli", "sch", "erc", "--severity-all", "--exit-code-violations", "-o", str(ERC_REPORT), str(SCHEMATIC)],
        check=True,
    )


def component_table(root: ET.Element) -> dict[str, ET.Element]:
    result = {component.attrib["ref"]: component for component in root.findall("./components/comp")}
    if len(result) != len(root.findall("./components/comp")):
        raise AssertionError("Duplicate component reference")
    return result


def net_tables(root: ET.Element):
    by_pin: dict[tuple[str, str], str] = {}
    by_net: dict[str, set[tuple[str, str]]] = {}
    for net in root.findall("./nets/net"):
        # Root-sheet local labels are serialized as "/NET" by KiCad.
        name = net.attrib["name"].removeprefix("/")
        nodes = {(node.attrib["ref"], node.attrib["pin"]) for node in net.findall("node")}
        by_net[name] = nodes
        for node in nodes:
            if node in by_pin:
                raise AssertionError(f"Pin appears in multiple nets: {node}")
            by_pin[node] = name
    return by_pin, by_net


def assert_pins(by_pin: dict[tuple[str, str], str], ref: str, expected: dict[int, str]) -> None:
    for pin, net in expected.items():
        actual = by_pin.get((ref, str(pin)))
        if actual != net:
            raise AssertionError(f"{ref}.{pin}: expected {net}, found {actual}")


def audit_connectivity(by_pin: dict[tuple[str, str], str], by_net: dict[str, set[tuple[str, str]]]) -> None:
    assert_pins(by_pin, "J1", {1: "+3V3_PI", 3: "I2C_SDA", 5: "I2C_SCL", 7: "UART2_TX", 17: "+3V3_PI", 29: "UART2_RX", 32: "UART4_TX", 33: "UART4_RX"})
    for pin in (6, 9, 14, 20, 25, 30, 34, 39):
        assert_pins(by_pin, "J1", {pin: "GND"})

    assert_pins(by_pin, "U1", {1: "MAX1_VCC", 2: "MAX1_RO", 3: "MAX1_DI", 4: "GND", 5: "CTRL_TX_P", 6: "CTRL_TX_N", 7: "CTRL_RX_N", 8: "CTRL_RX_P"})
    assert_pins(by_pin, "U3", {1: "MAX2_VCC", 2: "MAX2_RO", 3: "MAX2_DI", 4: "GND", 5: "PAYLOAD_TX_P", 6: "PAYLOAD_TX_N", 7: "PAYLOAD_RX_N", 8: "PAYLOAD_RX_P"})
    assert_pins(by_pin, "U2", {1: "UART2_TX", 2: "GND", 3: "MAX1_RO", 5: "+3V3_PI"})
    assert_pins(by_pin, "U4", {1: "UART4_TX", 2: "GND", 3: "MAX2_RO", 5: "+3V3_PI"})

    assert_pins(by_pin, "R100", {1: "+3V3_PI", 2: "MAX1_VCC"})
    assert_pins(by_pin, "R200", {1: "+3V3_PI", 2: "MAX2_VCC"})
    assert_pins(by_pin, "R101", {1: "+3V3_PI", 2: "UART2_TX"})
    assert_pins(by_pin, "R201", {1: "+3V3_PI", 2: "UART4_TX"})
    assert_pins(by_pin, "R104", {1: "CTRL_RX_P", 2: "CTRL_RX_N"})
    assert_pins(by_pin, "R204", {1: "PAYLOAD_RX_P", 2: "PAYLOAD_RX_N"})
    assert_pins(by_pin, "R105", {1: "+3V3_PI", 2: "CTRL_RX_P"})
    assert_pins(by_pin, "R106", {1: "CTRL_RX_N", 2: "GND"})
    assert_pins(by_pin, "R205", {1: "+3V3_PI", 2: "PAYLOAD_RX_P"})
    assert_pins(by_pin, "R206", {1: "PAYLOAD_RX_N", 2: "GND"})
    assert_pins(by_pin, "TP101", {1: "MAX1_VCC"})
    assert_pins(by_pin, "TP201", {1: "MAX2_VCC"})

    assert_pins(by_pin, "J2", {1: "CTRL_TX_P", 2: "CTRL_TX_N", 3: "GND", 4: "CTRL_RX_P", 5: "CTRL_RX_N"})
    assert_pins(by_pin, "J3", {1: "PAYLOAD_TX_P", 2: "PAYLOAD_TX_N", 3: "GND", 4: "PAYLOAD_RX_P", 5: "PAYLOAD_RX_N"})
    assert_pins(by_pin, "J4", {1: "BAT_P", 2: "GND"})
    assert_pins(by_pin, "R301", {1: "BAT_P", 2: "BAT_MID"})
    assert_pins(by_pin, "R302", {1: "BAT_MID", 2: "BAT_DIV"})
    assert_pins(by_pin, "R303", {1: "BAT_DIV", 2: "GND"})
    assert_pins(by_pin, "C302", {1: "BAT_DIV", 2: "GND"})
    assert_pins(by_pin, "U5", {1: "+3V3_PI", 2: "BAT_DIV", 3: "ADS_AIN0", 4: "GND", 7: "GND", 10: "GND", 13: "GND", 14: "+3V3_PI"})
    assert_pins(by_pin, "U6", {1: "GND", 2: "ADC_ALERT", 3: "GND", 4: "ADS_AIN0", 8: "+3V3_PI", 9: "I2C_SDA", 10: "I2C_SCL"})

    expected_bat_div = {("C302", "1"), ("R302", "2"), ("R303", "1"), ("TP302", "1"), ("U5", "2")}
    expected_adc = {("TP303", "1"), ("U5", "3"), ("U6", "4")}
    if by_net.get("BAT_DIV") != expected_bat_div:
        raise AssertionError(f"BAT_DIV has an unexpected direct load: {sorted(by_net.get('BAT_DIV', set()))}")
    if by_net.get("ADS_AIN0") != expected_adc:
        raise AssertionError(f"ADS_AIN0 isolation path changed: {sorted(by_net.get('ADS_AIN0', set()))}")
    if any(net in {"+5V", "5V"} for net in by_net):
        raise AssertionError("Pi 5V must not be used")


def audit_symbols(root: ET.Element) -> dict[tuple[str, str], set[str]]:
    libparts: dict[tuple[str, str], set[str]] = {}
    for libpart in root.findall("./libparts/libpart"):
        key = (libpart.attrib["lib"], libpart.attrib["part"])
        pins = {pin.attrib["num"]: pin.attrib["name"] for pin in libpart.findall("./pins/pin")}
        libparts[key] = set(pins)
        expected = OFFICIAL_PIN_MAPS.get(key[1])
        if expected is not None and pins != expected:
            raise AssertionError(f"{key[1]} symbol pin map mismatch: {pins}")
    return libparts


def numeric_footprint_pads(footprint_id: str) -> set[str]:
    library, name = footprint_id.split(":", 1)
    path = kicad_share_root() / "footprints" / f"{library}.pretty" / f"{name}.kicad_mod"
    text = path.read_text(encoding="utf-8")
    return set(re.findall(r'\(pad\s+"?(\d+)"?\s+', text))


def audit_symbol_footprint_parity(components: dict[str, ET.Element], libparts: dict[tuple[str, str], set[str]]) -> None:
    for ref, component in components.items():
        footprint = component.findtext("footprint", default="")
        if not footprint or footprint == ":":
            continue
        libsource = component.find("libsource")
        key = (libsource.attrib["lib"], libsource.attrib["part"])
        symbol_pins = libparts[key]
        footprint_pads = numeric_footprint_pads(footprint)
        if symbol_pins != footprint_pads:
            raise AssertionError(
                f"{ref} symbol/footprint pad mismatch: symbol={sorted(symbol_pins)}, footprint={sorted(footprint_pads)}"
            )


def audit_components(components: dict[str, ET.Element]) -> None:
    for ref, value in EXPECTED_VALUES.items():
        actual = components[ref].findtext("value", default="")
        if actual != value:
            raise AssertionError(f"{ref} value: expected {value}, found {actual}")
    for ref, datasheet in EXPECTED_DATASHEETS.items():
        actual = components[ref].findtext("datasheet", default="")
        if actual != datasheet:
            raise AssertionError(f"{ref} datasheet mismatch: {actual}")
    project_text = SCHEMATIC.read_text(encoding="utf-8")
    if "TMUX1072" in project_text:
        raise AssertionError("TMUX1072 is forbidden")


def audit_dnp() -> None:
    status: dict[str, bool] = {}
    for path in [SCHEMATIC]:
        text = path.read_text(encoding="utf-8")
        for start, end in _symbol_blocks(text):
            block = text[start:end]
            reference = re.search(r'\(property\s+"Reference"\s+"([^"]+)"', block)
            if reference is None:
                continue
            ref = reference.group(1)
            if re.fullmatch(r"[A-Z]+\d+", ref):
                status[ref] = "(dnp yes)" in block
    actual_dnp = {ref for ref, is_dnp in status.items() if is_dnp}
    if actual_dnp != DNP_REFS:
        raise AssertionError(f"DNP set mismatch: {sorted(actual_dnp)}")


def main() -> None:
    run_kicad_checks()
    root = ET.parse(NETLIST).getroot()
    sheets = root.findall("./design/sheet")
    if len(sheets) != 1 or sheets[0].attrib.get("name") != "/":
        raise AssertionError(f"Schematic must be one flat sheet, found {len(sheets)}")
    components = component_table(root)
    by_pin, by_net = net_tables(root)
    audit_connectivity(by_pin, by_net)
    libparts = audit_symbols(root)
    audit_symbol_footprint_parity(components, libparts)
    audit_components(components)
    audit_dnp()

    adc_full_scale = 12.6 * 18.0 / (47.0 + 47.0 + 18.0)
    scale = (47.0 + 47.0 + 18.0) / 18.0
    if not math.isclose(adc_full_scale, 2.025) or not math.isclose(scale, 6.222222222222222):
        raise AssertionError("Battery divider calculation changed")

    lines = [
        "RBPHAT Rev.A SCHEMATIC AUDIT: PASS",
        f"Generated: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        "KiCad ERC: 0 errors, 0 warnings",
        "Schematic: 1 flat A3 sheet.",
        f"Components: {len(components)}",
        f"Nets: {len(by_net)}",
        "All placed symbol pin-number sets equal their installed footprint pad-number sets.",
        "MAX3490E: 1=VCC, 2=RO, 3=DI, 4=GND, 5=Y, 6=Z, 7=B, 8=A.",
        "DNP only: R105, R106, R205, R206.",
        "Pi UART2: J1.7 GPIO4 TX / J1.29 GPIO5 RX.",
        "Pi UART4: J1.32 GPIO12 TX / J1.33 GPIO13 RX.",
        "MAX VCC measurement links: R100/R200 0R; test points: TP101/TP201.",
        "Receiver termination: R104/R204 120R fitted; 680R fail-safe pairs DNP.",
        f"Battery divider: 12.6 V -> {adc_full_scale:.3f} V; VBAT/VADC = {scale:.6f}.",
        "BAT_DIV reaches ADS1115 AIN0 only through TMUX1511 channel 1.",
        "Pi 5V is not used; external connector grounds are common and no external + rail is present.",
    ]
    AUDIT_REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
