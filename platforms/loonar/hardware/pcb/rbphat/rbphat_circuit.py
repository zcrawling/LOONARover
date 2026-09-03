#!/usr/bin/env python3
"""RBPHAT Rev.A electrical source of truth.

Generate the native KiCad 9 schematic with SKiDL 2.3.0. The circuit is kept as
code so every pin-to-net assignment can be reviewed and tested independently of
the GUI. The project-local ``rbphat.kicad_sym`` library is generated from the
audited symbols in ``generate_legacy_schematic.py`` using ``kicad-cli sym
upgrade``.
"""

import builtins
import os
from pathlib import Path

# SKiDL uses the standard power symbol library while rendering. Resolve the
# KiCad 9 library before importing SKiDL so the library scanner sees it.
for _symbol_dir in (
    os.environ.get("KICAD9_SYMBOL_DIR", ""),
    "/usr/share/kicad/symbols",
    "//wsl.localhost/Ubuntu-26.04/usr/share/kicad/symbols",
):
    if _symbol_dir and os.path.isdir(_symbol_dir):
        os.environ.setdefault("KICAD9_SYMBOL_DIR", _symbol_dir)
        break

import skidl
from skidl import POWER, KICAD9, Net, Part, Pin, subcircuit

from finalize_schematic import mark_dnp_files
from layout_single_schematic import layout_single_schematic


PROJECT_DIR = Path(__file__).resolve().parent
LOCAL_SYMBOL_DIR = str(PROJECT_DIR)

# Do not depend on user-global KiCad tables for audited symbols.
skidl.lib_search_paths[KICAD9].insert(0, LOCAL_SYMBOL_DIR)
if os.environ.get("KICAD9_SYMBOL_DIR") not in skidl.lib_search_paths[KICAD9]:
    skidl.lib_search_paths[KICAD9].append(os.environ["KICAD9_SYMBOL_DIR"])
skidl.set_default_tool(KICAD9)
NC = builtins.NC


FP = {
    "R0603": "Resistor_SMD:R_0603_1608Metric",
    "C0603": "Capacitor_SMD:C_0603_1608Metric",
    "SOIC8": "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
    "SOT236": "Package_TO_SOT_SMD:SOT-23-6",
    "SOT23": "Package_TO_SOT_SMD:SOT-23",
    "TSSOP14": "Package_SO:TSSOP-14_4.4x5mm_P0.65mm",
    "VSSOP10": "Package_SO:TSSOP-10_3x3mm_P0.5mm",
    "PI40": "Connector_PinSocket_2.54mm:PinSocket_2x20_P2.54mm_Vertical",
    "JST5": "Connector_JST:JST_GH_SM05B-GHS-TB_1x05-1MP_P1.25mm_Horizontal",
    "JST2": "Connector_JST:JST_GH_SM02B-GHS-TB_1x02-1MP_P1.25mm_Horizontal",
    "TP": "TestPoint:TestPoint_Plated_Hole_D2.0mm",
}


def part(symbol: str, ref: str, value: str, footprint: str, **kwargs) -> Part:
    """Instantiate an audited project-local symbol with an explicit footprint."""
    return Part(
        "rbphat",
        symbol,
        tool=KICAD9,
        ref=ref,
        value=value,
        footprint=footprint,
        **kwargs,
    )


def resistor(ref: str, value: str, n1: Net, n2: Net, *, dnp: bool = False) -> Part:
    item = part("R", ref, value, FP["R0603"], dnp=dnp)
    n1 += item[1]
    n2 += item[2]
    return item


def capacitor(ref: str, value: str, n1: Net, n2: Net) -> Part:
    item = part("C", ref, value, FP["C0603"])
    n1 += item[1]
    n2 += item[2]
    return item


def testpoint(ref: str, net: Net) -> Part:
    item = part("TESTPOINT", ref, net.name, FP["TP"])
    net += item[1]
    return item


def power_flag(ref: str, net: Net) -> Part:
    """Tell KiCad ERC that an externally supplied rail is intentionally driven."""
    item = part("PWR_FLAG", ref, "PWR_FLAG", "")
    net += item[1]
    return item


def nets(*names: str) -> dict[str, Net]:
    return {name: Net(name) for name in names}


N = nets(
    "+3V3_PI",
    "GND",
    "I2C_SDA",
    "I2C_SCL",
    "UART2_TX",
    "UART2_RX",
    "UART4_TX",
    "UART4_RX",
    "CTRL_TX_P",
    "CTRL_TX_N",
    "CTRL_RX_P",
    "CTRL_RX_N",
    "PAYLOAD_TX_P",
    "PAYLOAD_TX_N",
    "PAYLOAD_RX_P",
    "PAYLOAD_RX_N",
    "MAX1_VCC",
    "MAX2_VCC",
    "MAX1_DI",
    "MAX1_RO",
    "MAX2_DI",
    "MAX2_RO",
    "BUF1_TX",
    "BUF1_RX",
    "BUF2_TX",
    "BUF2_RX",
    "BAT_P",
    "BAT_MID",
    "BAT_DIV",
    "ADS_AIN0",
    "ADC_ALERT",
)

# External rails/signals are given explicit drive types so ERC understands the
# system boundary at J1/J2/J3/J4.
N["+3V3_PI"].drive = POWER
N["GND"].drive = POWER
N["BAT_P"].drive = POWER
N["MAX1_VCC"].drive = POWER
N["MAX2_VCC"].drive = POWER
for name in ("UART2_TX", "UART4_TX", "CTRL_RX_P", "CTRL_RX_N", "PAYLOAD_RX_P", "PAYLOAD_RX_N"):
    N[name].drive = Pin.drives.PUSHPULL
for name in ("I2C_SDA", "I2C_SCL"):
    N[name].drive = Pin.drives.TRISTATE


@subcircuit
def pi_header() -> None:
    global NC
    j1 = part("CONN_2X20", "J1", "Raspberry_Pi_2x20", FP["PI40"])
    used = {
        1: N["+3V3_PI"],
        3: N["I2C_SDA"],
        5: N["I2C_SCL"],
        6: N["GND"],
        7: N["UART2_TX"],
        9: N["GND"],
        14: N["GND"],
        17: N["+3V3_PI"],
        20: N["GND"],
        25: N["GND"],
        29: N["UART2_RX"],
        30: N["GND"],
        32: N["UART4_TX"],
        33: N["UART4_RX"],
        34: N["GND"],
        39: N["GND"],
    }
    for pin_no in range(1, 41):
        if pin_no in used:
            used[pin_no] += j1[pin_no]
        else:
            NC += j1[pin_no]
    testpoint("TP1", N["+3V3_PI"])
    testpoint("TP2", N["GND"])


@subcircuit
def rs422_channel(channel: int, ref_base: int, prefix: str, tx_net: str, rx_net: str) -> None:
    """One Pi UART -> LVC buffer -> MAX3490E -> protected JST-GH link."""
    max_ref = "U1" if channel == 1 else "U3"
    buf_ref = "U2" if channel == 1 else "U4"
    conn_ref = "J2" if channel == 1 else "J3"
    max_vcc = N[f"MAX{channel}_VCC"]
    max_di = N[f"MAX{channel}_DI"]
    max_ro = N[f"MAX{channel}_RO"]
    buf_tx = N[f"BUF{channel}_TX"]
    buf_rx = N[f"BUF{channel}_RX"]

    max3490 = part(
        "MAX3490E",
        max_ref,
        "MAX3490EESA+",
        FP["SOIC8"],
        datasheet="https://www.analog.com/media/en/technical-documentation/data-sheets/MAX3483E-MAX3491E.pdf",
    )
    # Official MAX3490E top view: 1 VCC, 2 RO, 3 DI, 4 GND,
    # 5 Y, 6 Z, 7 B, 8 A. Do not reorder these assignments.
    max_vcc += max3490[1]
    max_ro += max3490[2]
    max_di += max3490[3]
    N["GND"] += max3490[4]
    N[f"{prefix}_TX_P"] += max3490[5]
    N[f"{prefix}_TX_N"] += max3490[6]
    N[f"{prefix}_RX_N"] += max3490[7]
    N[f"{prefix}_RX_P"] += max3490[8]

    buffer = part(
        "SN74LVC2G34",
        buf_ref,
        "SN74LVC2G34DBVR",
        FP["SOT236"],
        datasheet="https://www.ti.com/lit/ds/symlink/sn74lvc2g34.pdf",
    )
    N[tx_net] += buffer[1]  # 1A: Pi TX input
    N["GND"] += buffer[2]
    max_ro += buffer[3]     # 2A: MAX RO input
    buf_rx += buffer[4]     # 2Y: Pi RX output
    N["+3V3_PI"] += buffer[5]
    buf_tx += buffer[6]     # 1Y: MAX DI output

    resistor(f"R{ref_base}", "0R", N["+3V3_PI"], max_vcc)
    resistor(f"R{ref_base + 1}", "47k", N["+3V3_PI"], N[tx_net])
    resistor(f"R{ref_base + 2}", "47R", buf_tx, max_di)
    resistor(f"R{ref_base + 3}", "47R", buf_rx, N[rx_net])
    resistor(f"R{ref_base + 4}", "120R", N[f"{prefix}_RX_P"], N[f"{prefix}_RX_N"])
    resistor(f"R{ref_base + 5}", "680R DNP", N["+3V3_PI"], N[f"{prefix}_RX_P"], dnp=True)
    resistor(f"R{ref_base + 6}", "680R DNP", N[f"{prefix}_RX_N"], N["GND"], dnp=True)
    capacitor(f"C{ref_base}", "100n", max_vcc, N["GND"])
    testpoint(f"TP{ref_base + 1}", max_vcc)

    for diode_offset, pair in enumerate(
        ((N[f"{prefix}_TX_P"], N[f"{prefix}_TX_N"]), (N[f"{prefix}_RX_P"], N[f"{prefix}_RX_N"])),
        start=1,
    ):
        line_1, line_2 = pair
        tvs = part("SM712", f"D{ref_base + diode_offset}", "SM712", FP["SOT23"])
        line_1 += tvs[1]
        line_2 += tvs[2]
        N["GND"] += tvs[3]

    connector = part("CONN_1X05", conn_ref, f"{prefix}_RS422", FP["JST5"])
    N[f"{prefix}_TX_P"] += connector[1]
    N[f"{prefix}_TX_N"] += connector[2]
    N["GND"] += connector[3]
    N[f"{prefix}_RX_P"] += connector[4]
    N[f"{prefix}_RX_N"] += connector[5]


@subcircuit
def battery_sense() -> None:
    global NC
    connector = part("CONN_1X02", "J4", "BAT_SENSE", FP["JST2"])
    N["BAT_P"] += connector[1]
    N["GND"] += connector[2]

    resistor("R301", "47k 0.1%", N["BAT_P"], N["BAT_MID"])
    resistor("R302", "47k 0.1%", N["BAT_MID"], N["BAT_DIV"])
    resistor("R303", "18k 0.1%", N["BAT_DIV"], N["GND"])
    capacitor("C302", "1uF", N["BAT_DIV"], N["GND"])

    tmux = part(
        "TMUX1511",
        "U5",
        "TMUX1511PWR",
        FP["TSSOP14"],
        datasheet="https://www.ti.com/lit/ds/symlink/tmux1511.pdf",
    )
    # Channel 1 is ON only while Pi 3V3 is present. TMUX1511 powered-off
    # protection isolates BAT_DIV from ADS_AIN0 when Pi 3V3 is zero.
    N["+3V3_PI"] += tmux[1]   # SEL1
    N["BAT_DIV"] += tmux[2]   # S1
    N["ADS_AIN0"] += tmux[3]  # D1
    N["GND"] += tmux[4]       # SEL2
    NC += tmux[5], tmux[6]
    N["GND"] += tmux[7]
    NC += tmux[8], tmux[9]
    N["GND"] += tmux[10]      # SEL3
    NC += tmux[11], tmux[12]
    N["GND"] += tmux[13]      # SEL4
    N["+3V3_PI"] += tmux[14]  # VDD
    capacitor("C300", "100n", N["+3V3_PI"], N["GND"])

    adc = part(
        "ADS1115",
        "U6",
        "ADS1115IDGSR",
        FP["VSSOP10"],
        datasheet="https://www.ti.com/lit/ds/symlink/ads1115.pdf",
    )
    N["GND"] += adc[1]         # ADDR=0 -> 0x48
    N["ADC_ALERT"] += adc[2]
    N["GND"] += adc[3]
    N["ADS_AIN0"] += adc[4]
    NC += adc[5], adc[6], adc[7]
    N["+3V3_PI"] += adc[8]
    N["I2C_SDA"] += adc[9]
    N["I2C_SCL"] += adc[10]
    capacitor("C301", "100n", N["+3V3_PI"], N["GND"])

    testpoint("TP301", N["BAT_P"])
    testpoint("TP302", N["BAT_DIV"])
    testpoint("TP303", N["ADS_AIN0"])
    testpoint("TP304", N["ADC_ALERT"])


def build() -> None:
    pi_header()
    rs422_channel(1, 100, "CTRL", "UART2_TX", "UART2_RX")
    rs422_channel(2, 200, "PAYLOAD", "UART4_TX", "UART4_RX")
    battery_sense()
    power_flag("#FLG0101", N["+3V3_PI"])
    power_flag("#FLG0102", N["GND"])
    power_flag("#FLG0103", N["MAX1_VCC"])
    power_flag("#FLG0104", N["MAX2_VCC"])

    # SKiDL's own connectivity ERC catches missing/incompatible pins before the
    # native file is emitted. KiCad ERC is run separately by verify_cad.sh.
    skidl.ERC()
    skidl.generate_schematic(
        tool=KICAD9,
        filepath=str(PROJECT_DIR),
        top_name="rbphat",
        title="RBPHAT Rev.A - Dual RS-422 and isolated battery sensing",
        # This circuit is small enough to review on one sheet. Do not split it
        # into hierarchical pages.
        flatness=1.0,
        auto_stub=True,
        auto_stub_fanout=1,
        label_clearance=True,
        grid_blocks=True,
        seed=int(os.environ.get("RBPHAT_LAYOUT_SEED", "1")),
        retries=4,
    )
    # SKiDL 2.3.0 preserves the DNP value text but does not propagate its dnp
    # keyword into KiCad's native instance flag. Keep the four optional bias
    # resistors unambiguously excluded from default assembly.
    mark_dnp_files()
    if not os.environ.get("RBPHAT_SKIP_LAYOUT"):
        layout_single_schematic()


if __name__ == "__main__":
    build()
