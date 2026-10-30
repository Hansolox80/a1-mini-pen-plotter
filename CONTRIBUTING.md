# Contributing to A1 Mini Pen Plotter

Thank you for your interest in contributing to **A1 Mini Pen Plotter**! This project is an open-source, engineering-grade preparation tool dedicated to transforming 2D SVG vector artwork into validated, safe G-code for the Bambu Lab A1 Mini.

We welcome bug reports, feature proposals, documentation improvements, and pull requests. Please take a moment to review these guidelines before contributing.

---

## Core Engineering Principles

When contributing code or proposals, keep the following principles in mind:

1. **Physical Machine Safety First**: We never assume printer behavior. Validation must be strict and conservative. Commands that could heat the nozzle on paper (`M104`, `M109`, `M140`, `M190`), engage extrusion (`E`), or trigger unverified physical wipe routines (`M1002`) are strictly prohibited.
2. **Never Assume Z=0 is Contact**: Physical pen holders extend below the nozzle by variable amounts. The application must treat pen calibration as hardware-dependent and provide clear warnings when unverified.
3. **Geometric Accuracy**: Coordinates must remain physically accurate within documented tolerances ($< 0.05\text{ mm}$). Curve flattening and transformations must preserve shapes without distortion.
4. **Professional Native UI/UX**: The interface follows professional CAD/CAM design standards (dark graphite theme, clean typography, 4/8px spacing, and vector icons). Emojis are never used as structural UI icons.

---

## Development Environment Setup

### Prerequisites
- **Python 3.12 or newer** (tested on Python 3.12, 3.13, and 3.15)
- **Git**
- **Supported OS**: Windows 10/11, Linux (Ubuntu/Debian/Fedora/Arch), or macOS 12+ (Apple Silicon & Intel)

### Installation Steps

1. **Fork and clone the repository:**
   ```bash
   git clone https://github.com/Hansolox80/a1-mini-pen-plotter.git
   cd a1-mini-pen-plotter
   ```

2. **Create and activate a virtual environment:**
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```powershell
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. **Generate resources and seed default profiles:**
   ```powershell
   python scripts\generate_assets.py
   ```

5. **Run the test suite:**
   ```powershell
   pytest -v
   ```

6. **Launch the application:**
   ```powershell
   python app\main.py
   ```

---

## Project Structure & Architecture

```text
A1-Mini-Pen-Plotter/
├── app/
│   ├── main.py                      # Application entry point & CLI flags
│   ├── ui/
│   │   ├── main_window.py           # Main application window & pipeline
│   │   ├── canvas.py                # 180×180 mm build plate visual workspace
│   │   ├── theme.py                 # Design tokens & QSS stylesheet
│   │   ├── icons.py                 # Vector Lucide SVG icon factory
│   │   ├── undo_commands.py         # QUndoCommand implementations
│   │   ├── panels/                  # Sidebar, Inspector, Simulator bar
│   │   └── dialogs/                 # Wizard, Validator, Settings
│   ├── core/
│   │   ├── models.py                # Dataclasses & types
│   │   ├── svg_parser.py            # SVG parser & matrix transforms
│   │   ├── coordinate_system.py     # Y-axis inversion & plate mapping
│   │   ├── geometry.py              # Curves, hatching, contours
│   │   ├── path_optimizer.py        # Nearest-Neighbor & 2-Opt optimizer
│   │   ├── gcode_generator.py       # G-code generation & templates
│   │   └── simulator.py             # Playback state engine
│   ├── machine/
│   │   ├── a1_mini.py               # Hardware specs & cold G-code
│   │   ├── profiles.py              # JSON profile manager
│   │   └── safety.py                # Mandatory safety validator
│   ├── export/
│   │   ├── gcode_exporter.py        # .gcode, .gcode.3mf, .svg, reports
│   │   └── project_exporter.py      # .a1plot project format
│   └── resources/                   # Vector logo and multi-size icon.ico
├── profiles/                        # Default machine and pen JSON files
├── examples/                        # Test SVG suite (11 files)
├── tests/                           # Unit & UI automated tests
├── docs/                            # Documentation & screenshots
├── scripts/                         # Build, release, and helper scripts
├── requirements.txt
├── A1_Mini_Pen_Plotter.spec
└── build_windows.bat
```

---

## Code Quality Standards

- **Code Style**: Adhere to PEP 8. Use meaningful variable and function names.
- **Type Annotations**: All new functions and methods should have comprehensive type hints.
- **Documentation**: Write clear docstrings for classes, methods, and modules. Document any assumptions regarding firmware compatibility.
- **Modular Design**: Keep core geometry and conversion logic independent of the UI layer so that every calculation can be tested headlessly.

---

## Testing Guidelines

Any contribution that modifies geometry conversion, SVG parsing, G-code generation, or safety validation **must** include automated tests in `tests/`:

- Run all automated tests:
  ```powershell
  pytest -v
  ```
- If adding support for new SVG elements, add an appropriate test case verifying geometric dimensions in `tests/test_engine.py`.
- If modifying UI interactions, update or add tests in `tests/test_ui.py`.

---

## Submitting Pull Requests

1. **Create a descriptive feature branch:**
   ```powershell
   git checkout -b feature/hatch-angle-presets
   ```
2. **Commit your changes with clear, concise messages:**
   ```powershell
   git commit -m "feat(fill): add preset selector for common hatching angles"
   ```
3. **Verify the complete build pipeline:**
   Run `build_windows.bat` or ensure all 20+ tests pass with zero warnings:
   ```powershell
   pytest -v
   ```
4. **Push to your fork and submit a Pull Request** against the `main` branch.
5. Fill out the Pull Request template completely, detailing what was changed and how it was tested.

---

## Reporting Issues

- **Bug Reports**: Use the [Bug Report template](.github/ISSUE_TEMPLATE/bug_report.md). Include the SVG file that caused the issue, your machine and pen profile settings, and the exact error output or log file from `%USERPROFILE%\.a1_mini_pen_plotter\logs\`.
- **Feature Requests**: Use the [Feature Request template](.github/ISSUE_TEMPLATE/feature_request.md). Explain the physical or workflow rationale behind the proposed feature.
