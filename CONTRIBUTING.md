# Contributing to A1 Mini Pen Plotter

Thank you for your interest in contributing to **A1 Mini Pen Plotter**! This project is an open-source, engineering-grade preparation tool dedicated to transforming 2D SVG vector artwork into validated, safe G-code for the Bambu Lab A1 Mini.

We welcome bug reports, feature proposals, documentation improvements, and pull requests. Please take a moment to review these guidelines before contributing.

---

## Core Engineering Principles

When contributing code or proposals, keep the following principles in mind:

1. **Physical Machine Safety First**: We never assume printer behavior. Validation must be strict and conservative. Commands that could heat the nozzle on paper (`M104`, `M109`, `M140`, `M190`), engage extrusion (`E`), or trigger unverified physical wipe routines (`M1002`) are strictly prohibited.
2. **Never Assume Z=0 is Contact**: Physical pen holders extend below the nozzle by variable amounts. The application must treat pen calibration as hardware-dependent and provide clear warnings when unverified.
3. **Geometric Accuracy**: Coordinates must remain physically accurate within documented tolerances ($< 0.05\text{ mm}$). Curve flattening and transformations must preserve shapes without distortion.
4. **Professional Native UI/UX**: The interface follows professional CAD/CAM design standards (consistent multi-theme token system across 13 Dark/Light themes, cross-platform custom window chrome, clean typography, 4/8px spacing, and vector icons). Emojis are never used as structural UI icons.

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
   # Windows (PowerShell)
   python -m venv .venv
   .\.venv\Scripts\activate
   ```
   ```bash
   # Linux / macOS
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. **Generate resources and seed default profiles:**
   ```bash
   python scripts/generate_assets.py
   ```

5. **Run the test suite:**
   ```bash
   # Windows / macOS
   pytest -v

   # Linux headless environments
   QT_QPA_PLATFORM=offscreen pytest -v
   ```

6. **Launch the application:**
   ```bash
   python app/main.py
   ```

---

## Project Structure & Architecture

```text
a1-mini-pen-plotter/
├── .github/
│   ├── ISSUE_TEMPLATE/              # bug_report.md, feature_request.md
│   ├── PULL_REQUEST_TEMPLATE.md
│   └── workflows/
│       └── build_and_test.yml       # Multiplatform CI (Windows, Linux, macOS)
├── app/
│   ├── __init__.py                  # Version & metadata (__version__)
│   ├── main.py                      # Application entry point & CLI flags
│   ├── ui/
│   │   ├── main_window.py           # Main application window & pipeline
│   │   ├── canvas.py                # 180×180 mm build plate visual workspace
│   │   ├── theme.py                 # 13 Dark/Light themes, QPalette & QSS
│   │   ├── theme_switch.py          # Animated Dark/Light toolbar switch
│   │   ├── window_chrome.py         # Cross-platform custom window chrome
│   │   ├── icons.py                 # Vector Lucide SVG icon factory
│   │   ├── undo_commands.py         # QUndoCommand implementations
│   │   ├── panels/                  # Sidebar, Inspector, Simulator bar
│   │   └── dialogs/                 # Wizard, Validator, Resize, Settings
│   ├── core/
│   │   ├── models.py                # Dataclasses & types
│   │   ├── svg_parser.py            # SVG parser & matrix transforms
│   │   ├── coordinate_system.py     # Y-axis inversion & plate mapping
│   │   ├── geometry.py              # Curves, hatching, contours
│   │   ├── path_optimizer.py        # Nearest-Neighbor & 2-Opt optimizer
│   │   ├── pipeline_worker.py       # Background QRunnable pipeline worker
│   │   ├── platform_utils.py        # OS-agnostic paths & system fonts
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
├── examples/                        # Test SVG suite (11 files) & sample output
├── tests/                           # 65 unit, fuzzing, stress, theme & UI tests
├── docs/                            # Architecture docs & screenshots
├── scripts/                         # Build, release, and helper scripts
├── CHANGELOG.md
├── CONTRIBUTING.md
├── SECURITY.md
├── pytest.ini
├── requirements.txt
├── A1_Mini_Pen_Plotter.spec
├── build_windows.bat
├── build_linux.sh
└── build_macos.sh
```

---

## Code Quality Standards

- **Code Style**: Adhere to PEP 8. Use meaningful variable and function names.
- **Type Annotations**: All new functions and methods should have comprehensive type hints.
- **Documentation**: Write clear docstrings for classes, methods, and modules. Document any assumptions regarding firmware compatibility.
- **Modular Design**: Keep core geometry and conversion logic independent of the UI layer so that every calculation can be tested headlessly.

---

## Testing Guidelines

Any contribution that modifies geometry conversion, SVG parsing, G-code generation, themes/window chrome, or safety validation **must** include automated tests in `tests/`:

- Run all automated tests:
  ```bash
  # Windows / macOS
  pytest -v

  # Linux headless environments
  QT_QPA_PLATFORM=offscreen pytest -v
  ```
- If adding support for new SVG elements, add an appropriate test case verifying geometric dimensions in `tests/test_engine.py`.
- If modifying UI interactions, update or add tests in `tests/test_ui.py` or `tests/test_themes.py`.
- Clearly distinguish automated software tests (`pytest` / CI) from physical Bambu Lab A1 Mini printer verification in your PR description; never claim physical hardware testing unless performed on real hardware.

---

## Submitting Pull Requests

1. **Create a descriptive feature branch:**
   ```bash
   git checkout -b feature/hatch-angle-presets
   ```
2. **Commit your changes with clear, concise messages:**
   ```bash
   git commit -m "feat(fill): add preset selector for common hatching angles"
   ```
3. **Verify the complete build & test pipeline:**
   Run the automated test suite (currently **65 automated tests**) and, if modifying packaging or UI, run the platform build script (`build_windows.bat`, `./build_linux.sh`, or `./build_macos.sh`):
   ```bash
   pytest -v
   ```
4. **Push to your fork and submit a Pull Request** against the `main` branch.
5. Fill out the [Pull Request template](.github/PULL_REQUEST_TEMPLATE.md) completely, detailing what was changed and how it was tested.

---

## Reporting Issues

- **Bug Reports**: Use the [Bug Report template](.github/ISSUE_TEMPLATE/bug_report.md). Include the SVG file that caused the issue, your machine and pen profile settings, and the exact error output or log file from `%USERPROFILE%\.a1_mini_pen_plotter\logs\` (Windows) or `~/.a1_mini_pen_plotter/logs/` (Linux/macOS).
- **Feature Requests**: Use the [Feature Request template](.github/ISSUE_TEMPLATE/feature_request.md). Explain the physical or workflow rationale behind the proposed feature.
