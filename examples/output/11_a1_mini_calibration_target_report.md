# A1 Mini Pen Plotter — Safety Validation Report
Overall Status: CRITICAL
Executable Export Allowed: NO (BLOCKED)
Machine Profile: Bambu Lab A1 Mini (180x180 mm)
Pen Profile: Fineliner 0.4mm (Micron / Staedtler) (Draw Z=14.00 mm, Pen-Up Z=18.00 mm)
Checked Movements: 271 | Checked G-code Lines: 361
Coordinate Bounds: X[0.00..140.00] Y[0.00..140.00] Z[14.00..18.00] mm

## Mandatory Physical Collision-Risk Warnings
- [COLLISION RISK] Software validation checks numeric coordinates only and cannot detect physical obstructions (such as binder clips, raised tape edges, warped paper, or an improperly seated pen holder).
- [COLLISION RISK] Pen profile 'Fineliner 0.4mm (Micron / Staedtler)' has not been marked as calibrated via the Calibration Wizard. Verify that Drawing Z (14.00 mm) matches your physical pen mount.
- [COLLISION RISK] Pen holder offset (+0.0, -22.0 mm) shifts the physical toolhead carriage relative to the pen tip. Ensure the toolhead clears the X-axis purge wiper and Z-pillar.

## Validation Findings (1 total)
- [CRITICAL] UNCALIBRATED_PEN_PROFILE: Pen Profile Not Physically Calibrated
  Pen profile 'Fineliner 0.4mm (Micron / Staedtler)' uses unverified default Z heights (Draw Z=14.00 mm, Up Z=18.00 mm). Physical calibration via the Pen Calibration Wizard is required before exporting execution-ready G-code (or enable Air Draw Mode to test safely in the air).

## Disclaimer
IMPORTANT SAFETY NOTICE: Software validation verifies coordinate bounds, feed rates, and command syntax, but CANNOT guarantee physical collision prevention. Always verify pen holder clearance, nozzle height relative to the pen tip, bed surface obstacles, and Z contact calibration manually before running on the Bambu Lab A1 Mini.
