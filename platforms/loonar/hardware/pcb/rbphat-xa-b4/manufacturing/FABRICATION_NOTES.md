# RBPHAT B4 — fabrication and assembly instructions

Current design: rbphat-xa-b4/rbphat.kicad_pcb. Do not mix B3 or earlier manufacturing files with this release.

- 65 x 56 mm, corner radius 3 mm; 4-layer FR4, nominal finished thickness 1.6 mm. Follow supplied stackup; In1.Cu and In2.Cu are GND planes. Confirm actual dielectric/copper stack with fabricator. No controlled impedance specification.
- Minimum trace/clearance 0.20 mm; via diameter/drill 0.60/0.30 mm; board edge copper clearance 0.30 mm. Do not shrink clearances or alter drill geometry.
- J1: 40 plated holes, finished diameter 1.02 mm. Confirm finished-hole tolerance fits PRT-16763 pins before manufacture.
- J2/J3/J4: 14 plated holes, finished diameter 0.95 +/-0.05 mm (manufacturer reference 0.9 +0.1/-0 mm). THREE unplated hook slots, 2.8 x 2.0 mm. Slots MUST be routed, not replaced with round holes. Four separate mounting holes are NPTH diameter 2.75 mm.
- SH1: one plated 3.2 mm hole, 6.4 mm copper pad, dedicated CHASSIS net. Both inner GND planes have a local exclusion. Do not connect CHASSIS to board GND, mounting holes, or Pi rails.
- Total drills: 126 plated (71 vias, 40 J1, 14 XA, 1 SH1); 7 unplated features (4 mounting holes, 3 slots).
- 61 top SMT parts. R107 and R207: 120 ohm, FITTED; both appear in paste and placement. No DNP parts in this release.
- Four PTH connectors: J1 on bottom; J2/J3/J4 on top. PTH connectors are intentionally absent from top-placement.csv. Match pin 1 in the native board and assembly drawing; verify assembly-house rotation conventions.
- J2/J3: S06B-XASK-1(LF)(SN), horizontal JST XA with hook, facing right/outward. J4: S02B-XASS-1(LF)(SN), horizontal JST XA with hook, facing left/outward. Do not substitute vertical or hookless versions.
- J2/J3 physical pin order: 1 TX+, 2 TX-, 3 RX+, 4 RX-, 5 GND, 6 SHIELD/CHASSIS. J4: 1 BAT_RAW, 2 GND. Wire by molded pin number, not by an assumed viewing direction.
- Housings: XAP-06V-1 x2 and XAP-02V-1 x1. SXA-001T-P0.6 contacts x14 plus spares. Apply JST crimp instructions and verify retention.
- SH1 requires a ring-terminal wire to the external chassis. Use M3 hardware, maximum washer OD 8 mm; keep all underside terminal/hardware protrusion <=3.5 mm. Prevent loose hardware and unintended contact to surrounding conductors. Actual chassis bonding and fit require first-article inspection.
- Keep the 16 mm socket body (PRT-16763) and nominal 19 mm PCB spacing. Pi 5 official Active Cooler; no underside components except J1. Nominal cooler envelope leaves 5.3 mm under HAT, before hardware/tolerances. Confirm actual insertion, spacers, screw/terminal clearance and cooling airflow on first assembly.
- Connector molded envelope height 7.6 mm. Mating housings project approximately 5.9 mm beyond board edge, plus wire bend/strain-relief space. Enclosure must provide this clearance.
- 3D XA files are simplified nominal envelope models, not manufacturer detailed solids. Fabrication geometry comes from the footprint and manufacturer drawing.
- Battery conversion ratio 8.222222; intended normal input 0–12.6 V. Firmware must use this ratio. 2 Mbps communication, power-off/backfeed behavior, thermal/EMC performance and mechanical fit need prototype measurements.

CAD validation: ERC 0 errors/0 warnings, PCB DRC 0, unrouted 0, schematic parity 0. This is a prototype fabrication release, not physical qualification. Obtain fabrication/assembly DFM acknowledgement, particularly finished holes, slots and connector orientation.

Manufacturer drawing: https://www.jst-mfg.com/product/pdf/eng/eXA-WB.pdf (local references/jst-xa.pdf).
