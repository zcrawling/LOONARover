# RBPHAT B3 fabrication specification

- Board: 65 x 56 mm, corner radius 3 mm; finished nominal thickness 1.6 mm.
- Four copper layers in order: F.Cu / In1.Cu GND / In2.Cu GND / B.Cu.
- Nominal copper: 35 um each layer; FR4, ENIG; green solder mask and white silkscreen.
- No controlled impedance certification specified. Internal dielectric dimensions in KiCad are a design starting stack; fabricator to confirm its 1.6 mm process stack.
- Minimum track/space: 0.20/0.20 mm. Minimum copper-to-board-edge: 0.30 mm.
- Through vias: 67, nominal drill 0.30 mm / copper diameter 0.60 mm.
- Header: 40 plated holes, FINISHED diameter 1.02 mm (not tool diameter).
- Mounting: 4 non-plated holes, diameter 2.75 mm; do not plate. Hole pitch 58 x 49 mm.
- Keep screw copper clearances as supplied. No routing/outline scaling.
- Gerber and Excellon share the board upper-left plot origin. Gerber X2/net attributes included.
- Header installed on BOTTOM: PRT-16763 H16 body, nominal 19 mm spacers.
- Remaining fitted parts are TOP SMD. R107/R207 default DNP.
- Default assembly paste excludes R107/R207. Header is a separate through-hole assembly operation.
- Electrical test against netlist is requested as part of board manufacture. CAD validation report is not a physical electrical test.
- No order has been submitted. Fabricator DFM and finished-hole/stackup confirmation remain fabrication steps.
