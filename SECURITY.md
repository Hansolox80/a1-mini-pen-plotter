# Security Policy

## Supported Versions

Security and safety fixes are applied to the active `main` branch and included in subsequent releases.

| Version | Supported |
| :--- | :--- |
| `3.11.x` (Latest) | Yes |
| `< 3.11.0` | No (upgrade to the latest release) |

---

## Reporting a Vulnerability

**Please do not report security vulnerabilities or safety-validator bypasses in public GitHub issues.**

Instead, use GitHub's **Security** tab (**Report a vulnerability** / Private Vulnerability Reporting) on the repository:

- [Report a vulnerability via GitHub Security Advisories](https://github.com/Hansolox80/a1-mini-pen-plotter/security/advisories/new)

When submitting a report, please include:
1. A clear description of the vulnerability or safety bypass and its potential impact.
2. Minimal reproduction steps or a sample `.svg`, `.a1plot`, or `.gcode` input.
3. Your operating system, Python version (if running from source), and application version.

If Private Vulnerability Reporting is temporarily unavailable on the repository, open a minimal issue requesting a private contact channel from the maintainer without posting exploit payloads or bypass inputs publicly.

---

## Security & Safety Scope

Areas of particular importance for **A1 Mini Pen Plotter** include:
- **SVG / XML Parsing (`app/core/svg_parser.py`)**: Protection against malformed XML, XXE/entity expansion (`defusedxml`), and NaN/Inf coordinate handling.
- **Safety Validator (`app/machine/safety.py`)**: Bypasses that could allow forbidden heating commands (`M104 > 0`, `M109`, `M140 > 0`, `M190`), extrusion moves (`E` axis), negative coordinates, out-of-bounds travel, or unsafe Z heights into exported `.gcode` or `.gcode.3mf` files.
- **Release Integrity**: Always verify downloaded release archives against the `SHA256SUMS.txt` file attached to each official [GitHub Release](https://github.com/Hansolox80/a1-mini-pen-plotter/releases).

---

## Mechanical Safety Disclaimer

Software validation reduces risk but does not replace physical machine verification. Always calibrate your pen offset using the built-in 6-Step Pen Calibration Wizard and perform an **Air Draw** dry run before plotting on a physical Bambu Lab A1 Mini.
