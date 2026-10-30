# A1 Mini Pen Plotter — Safety Validation Report
Overall Status: VALID
Executable Export Allowed: YES
Machine Profile: Bambu Lab A1 Mini (180x180 mm)
Pen Profile: Fineliner 0.4mm (Micron / Staedtler) (Draw Z=14.00 mm, Pen-Up Z=18.00 mm)
Checked Movements: 271 | Checked G-code Lines: 339
Coordinate Bounds: X[0.00..140.00] Y[0.00..140.00] Z[14.00..18.00] mm

## Mandatory Physical Collision-Risk Warnings
- [COLLISION RISK] Software validation checks numeric coordinates only and cannot detect physical obstructions (such as binder clips, raised tape edges, warped paper, or an improperly seated pen holder).
- [COLLISION RISK] Pen holder offset (+0.0, -22.0 mm) shifts the physical toolhead carriage relative to the pen tip. Ensure the toolhead clears the X-axis purge wiper and Z-pillar.

## Validation Findings (0 total)
- No validation issues detected.

## Disclaimer
IMPORTANT SAFETY NOTICE: Software validation verifies coordinate bounds, feed rates, and command syntax, but CANNOT guarantee physical collision prevention. Always verify pen holder clearance, nozzle height relative to the pen tip, bed surface obstacles, and Z contact calibration manually before running on the Bambu Lab A1 Mini.
