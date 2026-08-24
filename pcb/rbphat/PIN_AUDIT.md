# RBPHAT Rev.A pin audit

This table is the release gate for schematic capture and PCB update. A part is not
allowed into layout until the datasheet pin, KiCad symbol pin, and footprint pad
agree.

## U1, U3 — MAX3490EESA+ / SOIC-8

Authoritative source: Analog Devices, *MAX3483E–MAX3491E Rev.1*, MAX3490E
8-pin top-view pinout.

| Pad | Datasheet | Project symbol | SOIC-8 pad | Result |
|---:|---|---|---:|---|
| 1 | VCC | VCC | 1 | PASS |
| 2 | RO | RO | 2 | PASS |
| 3 | DI | DI | 3 | PASS |
| 4 | GND | GND | 4 | PASS |
| 5 | Y | Y | 5 | PASS |
| 6 | Z | Z | 6 | PASS |
| 7 | B | B | 7 | PASS |
| 8 | A | A | 8 | PASS |

Footprint: `Package_SO:SOIC-8_3.9x4.9mm_P1.27mm`.

Do not substitute the common but incorrect ordering `1=RO, 2=DI, 3=GND,
4=VCC`. The project-local symbol deliberately carries the official MAX3490E
ordering and a 12 Mbps description.

## U2, U4 — SN74LVC2G34DBVR / SOT-23-6

Authoritative source: Texas Instruments SN74LVC2G34 datasheet, DBV package.

| Pad | Datasheet | KiCad symbol | SOT-23-6 pad | Result |
|---:|---|---|---:|---|
| 1 | 1A | unit A input | 1 | PASS |
| 2 | GND | power unit GND | 2 | PASS |
| 3 | 2A | unit B input | 3 | PASS |
| 4 | 2Y | unit B output | 4 | PASS |
| 5 | VCC | power unit VCC | 5 | PASS |
| 6 | 1Y | unit A output | 6 | PASS |

Footprint: `Package_TO_SOT_SMD:SOT-23-6`.

Channel use for each UART:

- unit A: Pi TX -> 1A, 1Y -> MAX3490E DI
- unit B: MAX3490E RO -> 2A, 2Y -> Pi RX

## U5 — TMUX1511PWR / TSSOP-14

Authoritative source: Texas Instruments TMUX1511 Rev.B datasheet, PWR package.

| Pad | Datasheet | Project symbol | TSSOP-14 pad | Use | Result |
|---:|---|---|---:|---|---|
| 1 | SEL1 | SEL1 | 1 | Pi 3V3; channel ON only while powered | PASS |
| 2 | S1 | S1 | 2 | BAT_DIV | PASS |
| 3 | D1 | D1 | 3 | ADS_AIN0 | PASS |
| 4 | SEL2 | SEL2 | 4 | GND | PASS |
| 5 | S2 | S2 | 5 | NC | PASS |
| 6 | D2 | D2 | 6 | NC | PASS |
| 7 | GND | GND | 7 | GND | PASS |
| 8 | D3 | D3 | 8 | NC | PASS |
| 9 | S3 | S3 | 9 | NC | PASS |
| 10 | SEL3 | SEL3 | 10 | GND | PASS |
| 11 | D4 | D4 | 11 | NC | PASS |
| 12 | S4 | S4 | 12 | NC | PASS |
| 13 | SEL4 | SEL4 | 13 | GND | PASS |
| 14 | VDD | VDD | 14 | Pi 3V3 | PASS |

Footprint: `Package_SO:TSSOP-14_4.4x5mm_P0.65mm`.

## U6 — ADS1115IDGSR / VSSOP-10

Authoritative source: Texas Instruments ADS1115 datasheet, DGS package.

| Pad | Datasheet | KiCad symbol | TSSOP/VSSOP-10 pad | Use | Result |
|---:|---|---|---:|---|---|
| 1 | ADDR | ADDR | 1 | GND, address 0x48 | PASS |
| 2 | ALERT/RDY | ALERT/RDY | 2 | test point, otherwise NC | PASS |
| 3 | GND | GND | 3 | GND | PASS |
| 4 | AIN0 | AIN0 | 4 | TMUX1511 D1 | PASS |
| 5 | AIN1 | AIN1 | 5 | NC | PASS |
| 6 | AIN2 | AIN2 | 6 | NC | PASS |
| 7 | AIN3 | AIN3 | 7 | NC | PASS |
| 8 | VDD | VDD | 8 | Pi 3V3 | PASS |
| 9 | SDA | SDA | 9 | Pi GPIO2 / pin 3 | PASS |
| 10 | SCL | SCL | 10 | Pi GPIO3 / pin 5 | PASS |

Footprint: `Package_SO:TSSOP-10_3x3mm_P0.5mm` (DGS land pattern).

## Raspberry Pi 40-pin header nets used

| Physical pin | Signal | RBPHAT use |
|---:|---|---|
| 1, 17 | 3V3 | logic/ADC/TMUX supply; MAX supplies via individual 0R |
| 3 | GPIO2 / SDA1 | ADS1115 SDA |
| 5 | GPIO3 / SCL1 | ADS1115 SCL |
| 7 | GPIO4 / UART2_TX | U2 1A; 47k pull-up to 3V3 |
| 29 | GPIO5 / UART2_RX | U2 2Y |
| 32 | GPIO12 / UART4_TX | U4 1A; 47k pull-up to 3V3 |
| 33 | GPIO13 / UART4_RX | U4 2Y |
| 6, 9, 14, 20, 25, 30, 34, 39 | GND | plane |

## Source links

- MAX3490E: <https://www.analog.com/media/en/technical-documentation/data-sheets/MAX3483E-MAX3491E.pdf>
- SN74LVC2G34: <https://www.ti.com/lit/ds/symlink/sn74lvc2g34.pdf>
- TMUX1511: <https://www.ti.com/lit/ds/symlink/tmux1511.pdf>
- ADS1115: <https://www.ti.com/lit/ds/symlink/ads1115.pdf>
- Raspberry Pi RP1 alternate functions: <https://datasheets.raspberrypi.com/rp1/rp1-peripherals.pdf>

