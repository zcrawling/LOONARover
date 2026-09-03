#!/usr/bin/env python3
"""Generate the auditable legacy source used once to bootstrap KiCad 9.

The converted .kicad_sch is the design deliverable. This generator remains in
the repository so symbol pin numbers and schematic net intent can be reviewed as
plain text and regenerated deterministically.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parent


def legacy_library() -> str:
    symbols: list[str] = []

    def add(name: str, ref: str, footprint: str, draw: list[str]) -> None:
        symbols.extend(
            [
                f"#\n# {name}\n#",
                f"DEF {name} {ref} 0 30 Y Y 1 F N",
                f'F0 "{ref}" 0 100 50 H V C CNN',
                f'F1 "{name}" 0 -100 50 H V C CNN',
                f'F2 "{footprint}" 0 0 50 H I C CNN',
                'F3 "" 0 0 50 H I C CNN',
                "DRAW",
                *draw,
                "ENDDRAW",
                "ENDDEF",
            ]
        )

    add(
        "MAX3490E",
        "U",
        "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
        [
            "S -300 -400 300 400 0 1 10 f",
            "X VCC 1 0 -600 200 D 40 40 1 1 W",
            "X RO 2 -500 -200 200 R 40 40 1 1 O",
            "X DI 3 -500 200 200 R 40 40 1 1 I",
            "X GND 4 0 600 200 U 40 40 1 1 W",
            "X Y 5 500 300 200 L 40 40 1 1 O",
            "X Z 6 500 100 200 L 40 40 1 1 O",
            "X B 7 500 -100 200 L 40 40 1 1 I",
            "X A 8 500 -300 200 L 40 40 1 1 I",
        ],
    )
    add(
        "SN74LVC2G34",
        "U",
        "Package_TO_SOT_SMD:SOT-23-6",
        [
            "S -300 -350 300 350 0 1 10 f",
            "X 1A 1 -500 -200 200 R 40 40 1 1 I",
            "X GND 2 0 550 200 U 40 40 1 1 W",
            "X 2A 3 -500 200 200 R 40 40 1 1 I",
            "X 2Y 4 500 200 200 L 40 40 1 1 O",
            "X VCC 5 0 -550 200 D 40 40 1 1 W",
            "X 1Y 6 500 -200 200 L 40 40 1 1 O",
        ],
    )
    add(
        "TMUX1511",
        "U",
        "Package_SO:TSSOP-14_4.4x5mm_P0.65mm",
        [
            "S -400 -600 400 600 0 1 10 f",
            "X SEL1 1 -600 -450 200 R 35 35 1 1 I",
            "X S1 2 -600 -250 200 R 35 35 1 1 B",
            "X D1 3 600 -250 200 L 35 35 1 1 B",
            "X SEL2 4 -600 -50 200 R 35 35 1 1 I",
            "X S2 5 -600 150 200 R 35 35 1 1 B",
            "X D2 6 600 150 200 L 35 35 1 1 B",
            "X GND 7 0 800 200 U 35 35 1 1 W",
            "X D3 8 600 350 200 L 35 35 1 1 B",
            "X S3 9 -600 350 200 R 35 35 1 1 B",
            "X SEL3 10 -600 550 200 R 35 35 1 1 I",
            "X D4 11 600 550 200 L 35 35 1 1 B",
            "X S4 12 600 50 200 L 35 35 1 1 B",
            "X SEL4 13 600 -50 200 L 35 35 1 1 I",
            "X VDD 14 0 -800 200 D 35 35 1 1 W",
        ],
    )
    add(
        "ADS1115",
        "U",
        "Package_SO:TSSOP-10_3x3mm_P0.5mm",
        [
            "S -400 -500 400 500 0 1 10 f",
            "X ADDR 1 600 350 200 L 35 35 1 1 I",
            "X ALERT 2 600 150 200 L 35 35 1 1 O",
            "X GND 3 0 700 200 U 35 35 1 1 W",
            "X AIN0 4 -600 -300 200 R 35 35 1 1 I",
            "X AIN1 5 -600 -100 200 R 35 35 1 1 I",
            "X AIN2 6 -600 100 200 R 35 35 1 1 I",
            "X AIN3 7 -600 300 200 R 35 35 1 1 I",
            "X VDD 8 0 -700 200 D 35 35 1 1 W",
            "X SDA 9 600 -250 200 L 35 35 1 1 B",
            "X SCL 10 600 -450 200 L 35 35 1 1 I",
        ],
    )
    add(
        "R",
        "R",
        "Resistor_SMD:R_0603_1608Metric",
        [
            "S -100 -50 100 50 0 1 10 N",
            "X 1 1 -200 0 100 R 40 40 1 1 P",
            "X 2 2 200 0 100 L 40 40 1 1 P",
        ],
    )
    add(
        "C",
        "C",
        "Capacitor_SMD:C_0603_1608Metric",
        [
            "P 2 0 1 12 -20 -70 -20 70 N",
            "P 2 0 1 12 20 -70 20 70 N",
            "X 1 1 -200 0 180 R 40 40 1 1 P",
            "X 2 2 200 0 180 L 40 40 1 1 P",
        ],
    )
    add(
        "SM712",
        "D",
        "Package_TO_SOT_SMD:SOT-23",
        [
            "S -150 -100 150 100 0 1 10 f",
            "X LINE1 1 -300 0 150 R 35 35 1 1 P",
            "X LINE2 2 300 0 150 L 35 35 1 1 P",
            "X GND 3 0 300 200 U 35 35 1 1 P",
        ],
    )
    add(
        "TESTPOINT",
        "TP",
        "TestPoint:TestPoint_Plated_Hole_D2.0mm",
        [
            "C 0 0 50 0 1 10 N",
            "X 1 1 -200 0 150 R 40 40 1 1 P",
        ],
    )
    add(
        "PWR_FLAG",
        "#FLG",
        "",
        [
            "P 4 0 1 0 0 0 -50 -75 0 -150 50 -75 N",
            "X pwr 1 0 200 200 U 40 40 1 1 w",
        ],
    )

    def connector(name: str, pins: int, footprint: str, two_columns: bool = False) -> None:
        draw = ["S -200 -1100 200 1100 0 1 10 f"] if pins == 40 else [f"S -150 {-pins*70} 150 {pins*70} 0 1 10 f"]
        if two_columns:
            for number in range(1, pins + 1):
                row = (number - 1) // 2
                y = -950 + row * 100
                if number % 2:
                    draw.append(f"X {number} {number} -400 {y} 200 R 30 30 1 1 P")
                else:
                    draw.append(f"X {number} {number} 400 {y} 200 L 30 30 1 1 P")
        else:
            start = -((pins - 1) * 100) // 2
            for number in range(1, pins + 1):
                draw.append(f"X {number} {number} -350 {start + (number-1)*100} 200 R 30 30 1 1 P")
        add(name, "J", footprint, draw)

    connector(
        "CONN_2X20",
        40,
        "Connector_PinSocket_2.54mm:PinSocket_2x20_P2.54mm_Vertical",
        True,
    )
    connector(
        "CONN_1X05",
        5,
        "Connector_JST:JST_GH_SM05B-GHS-TB_1x05-1MP_P1.25mm_Horizontal",
    )
    connector(
        "CONN_1X02",
        2,
        "Connector_JST:JST_GH_SM02B-GHS-TB_1x02-1MP_P1.25mm_Horizontal",
    )
    return "\n".join(["EESchema-LIBRARY Version 2.4", "#encoding utf-8", *symbols, "#", "#End Library", ""])


class Schematic:
    def __init__(self) -> None:
        self.lines = [
            "EESchema Schematic File Version 4",
            "LIBS:rbphat-cache",
            "EELAYER 29 0",
            "EELAYER END",
            "$Descr A3 16535 11693",
            "Sheet 1 1",
            'Title "RBPHAT Rev.A"',
            'Date "2026-08-24"',
            'Rev "A"',
            'Comp "LOONAR"',
            'Comment1 "MAX3490E + SN74LVC2G34 dual RS-422; TMUX1511 battery isolation"',
            'Comment2 "Release gate: datasheet / symbol / footprint pin audit"',
            'Comment3 "Rev.A fault test: Teensy ON + Pi 3V3 OFF"',
            'Comment4 "MAX3490E pins: 1 VCC, 2 RO, 3 DI, 4 GND, 5 Y, 6 Z, 7 B, 8 A"',
            "$EndDescr",
        ]
        self.uid = 0x68000000

    def component(
        self,
        symbol: str,
        ref: str,
        value: str,
        footprint: str,
        x: int,
        y: int,
        *,
        datasheet: str = "",
        dnp: bool = False,
    ) -> None:
        self.uid += 1
        self.lines.extend(
            [
                "$Comp",
                f"L {symbol} {ref}",
                f"U 1 1 {self.uid:08X}",
                f"P {x} {y}",
                f'F 0 "{ref}" H {x} {y-150} 50  0000 C CNN',
                f'F 1 "{value}" H {x} {y+150} 50  0000 C CNN',
                f'F 2 "{footprint}" H {x} {y} 50  0001 C CNN',
                f'F 3 "{datasheet}" H {x} {y} 50  0001 C CNN',
            ]
        )
        if dnp:
            self.lines.append(f'F 4 "DNP" H {x} {y} 50  0001 C CNN "DNP"')
        self.lines.extend([f"\t1    {x} {y}", "\t1    0    0    -1", "$EndComp"])

    def endpoint(self, x: int, y: int, rel: tuple[int, int]) -> tuple[int, int]:
        return x + rel[0], y - rel[1]

    def label_pin(self, x: int, y: int, rel: tuple[int, int], net: str) -> None:
        px, py = self.endpoint(x, y, rel)
        if rel[0] < 0:
            qx, qy = px - 100, py
        elif rel[0] > 0:
            qx, qy = px + 100, py
        elif rel[1] < 0:
            qx, qy = px, py + 100
        else:
            qx, qy = px, py - 100
        self.lines.extend(
            [
                f"Wire Wire Line\n\t{px} {py} {qx} {qy}",
                f"Text Label {qx} {qy} 0    40   ~ 0",
                net,
            ]
        )

    def no_connect(self, x: int, y: int, rel: tuple[int, int]) -> None:
        px, py = self.endpoint(x, y, rel)
        self.lines.append(f"NoConn ~ {px} {py}")

    def note(self, x: int, y: int, text: str, size: int = 80) -> None:
        self.lines.extend([f"Text Notes {x} {y} 0    {size}   ~ 16", text])

    def finish(self) -> str:
        return "\n".join([*self.lines, "$EndSCHEMATC", ""])


MAX_PINS = {
    1: (0, -600), 2: (-500, -200), 3: (-500, 200), 4: (0, 600),
    5: (500, 300), 6: (500, 100), 7: (500, -100), 8: (500, -300),
}
BUF_PINS = {1: (-500, -200), 2: (0, 550), 3: (-500, 200), 4: (500, 200), 5: (0, -550), 6: (500, -200)}
TMUX_PINS = {
    1: (-600, -450), 2: (-600, -250), 3: (600, -250), 4: (-600, -50),
    5: (-600, 150), 6: (600, 150), 7: (0, 800), 8: (600, 350),
    9: (-600, 350), 10: (-600, 550), 11: (600, 550), 12: (600, 50),
    13: (600, -50), 14: (0, -800),
}
ADC_PINS = {
    1: (600, 350), 2: (600, 150), 3: (0, 700), 4: (-600, -300),
    5: (-600, -100), 6: (-600, 100), 7: (-600, 300), 8: (0, -700),
    9: (600, -250), 10: (600, -450),
}


def make_schematic() -> str:
    s = Schematic()
    fp_r = "Resistor_SMD:R_0603_1608Metric"
    fp_c = "Capacitor_SMD:C_0603_1608Metric"
    fp_tp = "TestPoint:TestPoint_Plated_Hole_D2.0mm"

    s.note(600, 450, "RBPHAT Rev.A — VERIFIED PINOUT / POWER-OFF TESTABLE", 110)
    s.note(600, 650, "Pi reboot with 3V3 alive is normal; framing recovery is firmware responsibility", 65)

    # Raspberry Pi header.
    j1x, j1y = 1300, 2800
    s.component("CONN_2X20", "J1", "Raspberry_Pi_2x20", "Connector_PinSocket_2.54mm:PinSocket_2x20_P2.54mm_Vertical", j1x, j1y)
    odd_left = {n: (-400, -950 + ((n - 1) // 2) * 100) for n in range(1, 41, 2)}
    even_right = {n: (400, -950 + ((n - 1) // 2) * 100) for n in range(2, 41, 2)}
    header = {**odd_left, **even_right}
    used = {
        1: "+3V3_PI", 3: "I2C_SDA", 5: "I2C_SCL", 6: "GND", 7: "UART2_TX",
        9: "GND", 14: "GND", 17: "+3V3_PI", 20: "GND", 25: "GND", 29: "UART2_RX",
        30: "GND", 32: "UART4_TX", 33: "UART4_RX", 34: "GND", 39: "GND",
    }
    for pin, rel in header.items():
        if pin in used:
            s.label_pin(j1x, j1y, rel, used[pin])
        else:
            s.no_connect(j1x, j1y, rel)

    # Power flags and common test points.
    s.component("PWR_FLAG", "#FLG01", "PWR_FLAG", "", 900, 650)
    s.label_pin(900, 650, (0, 200), "+3V3_PI")
    s.component("PWR_FLAG", "#FLG02", "PWR_FLAG", "", 1300, 650)
    s.label_pin(1300, 650, (0, 200), "GND")
    for ref, net, pos in [("TP1", "+3V3_PI", (1900, 650)), ("TP2", "GND", (2400, 650))]:
        s.component("TESTPOINT", ref, net, fp_tp, *pos)
        s.label_pin(*pos, (-200, 0), net)

    def resistor(ref: str, value: str, pos: tuple[int, int], n1: str, n2: str, *, dnp: bool = False, footprint: str = fp_r) -> None:
        s.component("R", ref, value, footprint, *pos, dnp=dnp)
        s.label_pin(*pos, (-200, 0), n1)
        s.label_pin(*pos, (200, 0), n2)

    def capacitor(ref: str, value: str, pos: tuple[int, int], n1: str, n2: str) -> None:
        s.component("C", ref, value, fp_c, *pos)
        s.label_pin(*pos, (-200, 0), n1)
        s.label_pin(*pos, (200, 0), n2)

    def uart_block(base_y: int, channel: int) -> None:
        if channel == 1:
            u_max, u_buf, con = "U1", "U2", "J2"
            prefix, gpio_tx, gpio_rx, dbase = "CTRL", "UART2_TX", "UART2_RX", 100
        else:
            u_max, u_buf, con = "U3", "U4", "J3"
            prefix, gpio_tx, gpio_rx, dbase = "PAYLOAD", "UART4_TX", "UART4_RX", 200
        s.note(3300, base_y - 900, f"UART{2 if channel == 1 else 4} / {prefix} RS-422", 80)
        bx, by = 4200, base_y
        mx, my = 6800, base_y
        s.component("SN74LVC2G34", u_buf, "SN74LVC2G34DBVR", "Package_TO_SOT_SMD:SOT-23-6", bx, by, datasheet="https://www.ti.com/lit/ds/symlink/sn74lvc2g34.pdf")
        buf_nets = {1: gpio_tx, 2: "GND", 3: f"MAX{channel}_RO", 4: f"BUF{channel}_RX", 5: "+3V3_PI", 6: f"BUF{channel}_TX"}
        for pin, net in buf_nets.items():
            s.label_pin(bx, by, BUF_PINS[pin], net)
        s.component("MAX3490E", u_max, "MAX3490EESA+", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", mx, my, datasheet="https://www.analog.com/media/en/technical-documentation/data-sheets/MAX3483E-MAX3491E.pdf")
        max_nets = {
            1: f"MAX{channel}_VCC", 2: f"MAX{channel}_RO", 3: f"MAX{channel}_DI", 4: "GND",
            5: f"{prefix}_TX_P", 6: f"{prefix}_TX_N", 7: f"{prefix}_RX_N", 8: f"{prefix}_RX_P",
        }
        for pin, net in max_nets.items():
            s.label_pin(mx, my, MAX_PINS[pin], net)

        resistor(f"R{dbase+0}", "0R", (6000, base_y - 650), "+3V3_PI", f"MAX{channel}_VCC")
        resistor(f"R{dbase+1}", "47k", (3600, base_y - 550), "+3V3_PI", gpio_tx)
        resistor(f"R{dbase+2}", "47R", (5400, base_y - 200), f"BUF{channel}_TX", f"MAX{channel}_DI")
        resistor(f"R{dbase+3}", "47R", (5400, base_y + 250), f"BUF{channel}_RX", gpio_rx)
        capacitor(f"C{dbase+0}", "100n", (7400, base_y - 650), f"MAX{channel}_VCC", "GND")
        resistor(f"R{dbase+4}", "120R", (8200, base_y), f"{prefix}_RX_P", f"{prefix}_RX_N")
        resistor(f"R{dbase+5}", "680R DNP", (8200, base_y - 450), "+3V3_PI", f"{prefix}_RX_P", dnp=True)
        resistor(f"R{dbase+6}", "680R DNP", (8200, base_y + 450), f"{prefix}_RX_N", "GND", dnp=True)

        tp_ref = f"TP{dbase+1}"
        s.component("TESTPOINT", tp_ref, f"MAX{channel}_VCC", fp_tp, 7400, base_y - 350)
        s.label_pin(7400, base_y - 350, (-200, 0), f"MAX{channel}_VCC")

        for idx, pair in enumerate(((f"{prefix}_TX_P", f"{prefix}_TX_N"), (f"{prefix}_RX_P", f"{prefix}_RX_N")), start=1):
            dx, dy = 9100, base_y - 250 + (idx - 1) * 500
            s.component("SM712", f"D{dbase+idx}", "SM712", "Package_TO_SOT_SMD:SOT-23", dx, dy)
            s.label_pin(dx, dy, (-300, 0), pair[0])
            s.label_pin(dx, dy, (300, 0), pair[1])
            s.label_pin(dx, dy, (0, 300), "GND")

        jx, jy = 10500, base_y
        s.component("CONN_1X05", con, f"{prefix}_RS422", "Connector_JST:JST_GH_SM05B-GHS-TB_1x05-1MP_P1.25mm_Horizontal", jx, jy)
        conn_rels = {n: (-350, -200 + (n - 1) * 100) for n in range(1, 6)}
        conn_nets = {1: f"{prefix}_TX_P", 2: f"{prefix}_TX_N", 3: "GND", 4: f"{prefix}_RX_P", 5: f"{prefix}_RX_N"}
        for pin, net in conn_nets.items():
            s.label_pin(jx, jy, conn_rels[pin], net)

    uart_block(1900, 1)
    uart_block(4900, 2)

    # Battery divider, powered-off isolation, and ADC.
    s.note(3300, 6900, "3S BATTERY SENSE / POWERED-OFF ISOLATION", 85)
    j4x, j4y = 3700, 7700
    s.component("CONN_1X02", "J4", "BAT_SENSE", "Connector_JST:JST_GH_SM02B-GHS-TB_1x02-1MP_P1.25mm_Horizontal", j4x, j4y)
    s.label_pin(j4x, j4y, (-350, -50), "BAT_P")
    s.label_pin(j4x, j4y, (-350, 50), "GND")
    resistor("R301", "47k 0.1%", (4700, 7400), "BAT_P", "BAT_MID")
    resistor("R302", "47k 0.1%", (5500, 7400), "BAT_MID", "BAT_DIV")
    resistor("R303", "18k 0.1%", (5500, 7900), "BAT_DIV", "GND")
    capacitor("C302", "1uF", (5500, 8300), "BAT_DIV", "GND")

    tx, ty = 7200, 7700
    s.component("TMUX1511", "U5", "TMUX1511PWR", "Package_SO:TSSOP-14_4.4x5mm_P0.65mm", tx, ty, datasheet="https://www.ti.com/lit/ds/symlink/tmux1511.pdf")
    tmux_nets = {1: "+3V3_PI", 2: "BAT_DIV", 3: "ADS_AIN0", 4: "GND", 7: "GND", 10: "GND", 13: "GND", 14: "+3V3_PI"}
    for pin, rel in TMUX_PINS.items():
        if pin in tmux_nets:
            s.label_pin(tx, ty, rel, tmux_nets[pin])
        else:
            s.no_connect(tx, ty, rel)
    capacitor("C300", "100n", (7200, 6800), "+3V3_PI", "GND")

    ax, ay = 9400, 7700
    s.component("ADS1115", "U6", "ADS1115IDGSR", "Package_SO:TSSOP-10_3x3mm_P0.5mm", ax, ay, datasheet="https://www.ti.com/lit/ds/symlink/ads1115.pdf")
    adc_nets = {1: "GND", 2: "ADC_ALERT", 3: "GND", 4: "ADS_AIN0", 8: "+3V3_PI", 9: "I2C_SDA", 10: "I2C_SCL"}
    for pin, rel in ADC_PINS.items():
        if pin in adc_nets:
            s.label_pin(ax, ay, rel, adc_nets[pin])
        else:
            s.no_connect(ax, ay, rel)
    capacitor("C301", "100n", (9400, 6800), "+3V3_PI", "GND")

    for ref, net, pos in [
        ("TP301", "BAT_P", (4300, 8600)),
        ("TP302", "BAT_DIV", (5600, 8600)),
        ("TP303", "ADS_AIN0", (7600, 8600)),
        ("TP304", "ADC_ALERT", (9900, 8600)),
    ]:
        s.component("TESTPOINT", ref, net, fp_tp, *pos)
        s.label_pin(*pos, (-200, 0), net)

    s.note(3300, 9200, "Divider: 47k + 47k / 18k, 0.1%; 12.6V -> ~2.025V; VBAT = VADC x 6.222222", 60)
    s.note(3300, 9400, "TMUX1511 SEL1=Pi3V3: ON while Pi powered, high-Z when Pi3V3=0", 60)
    s.note(3300, 9600, "Test power: Pi USB-C 5V; Teensy separate PSU; GND common only; never tie positive rails", 60)
    return s.finish()


def main() -> None:
    (ROOT / "rbphat-cache.lib").write_text(legacy_library(), encoding="utf-8", newline="\n")
    (ROOT / "rbphat.sch").write_text(make_schematic(), encoding="utf-8", newline="\n")
    (ROOT / "rbphat.pro").write_text("update=0\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()

