# Changelog

All notable changes to the **A1 Mini Pen Plotter** project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.10.1] - 2026-10-30

### Added
- **Exhaustive Deep End-to-End Stress Test Suite (`tests/test_deep_end_to_end_stress.py`)**:
  - Full gallery traversal across all 11 built-in sample SVGs with multiple curve precisions (0.05 mm, 0.2 mm) and all 3 workflow modes (`BAMBU_SD_DIRECT`, `BAMBU_STUDIO_3MF`, `STANDARD_GCODE`), validating file generation for `.gcode`, `.gcode.3mf`, `.svg`, and `.md` reports.
  - Algorithmic geometry benchmarking: Archimedean spirals (600 points), concentric circular arrays (30 rings), and order-4 Hilbert space-filling fractals (256 vertices) verifying path length equivalence across optimization modes.
  - Geometric containment testing for hatching and concentric contour fills on complex non-convex multipolygons with holes.
  - Real-time simulation transport engine stress: step-by-step monotonicity, continuous scrub seeking, and playback across speeds from 0.25x to 25x.
  - Deep Bambu Studio `.gcode.3mf` container inspection: ZIP archive hierarchy, embedded slice configuration (`Metadata/slice_info.config`), thumbnail PNG validation, and cryptographic MD5 integrity verification against `plate_1.gcode.md5`.
  - 50-step bidirectional Undo/Redo state roundtrip testing on `QUndoStack`.
  - 25-cycle repetitive pipeline endurance test verifying zero memory leaks or unhandled exceptions under continuous SVG loads, 2-Opt optimizations, and project resets.

### Fixed
- **60+ FPS Canvas Dragging & Rendering Performance Overhaul**:
  - Eliminated full toolpath, 2-Opt optimization, and G-code generation recomputations on every sub-pixel mouse move event during canvas dragging.
  - Implemented dynamic hardware-accelerated layer translation (`QPainter::translate`) during interactive dragging, decoupling canvas movement from backend geometry calculation.
  - Batched trajectory rendering using native Qt `drawLines` with precomputed coordinate transforms, accelerating vector display by up to 50x and eliminating micro-stutters.
  - Deferred pipeline recomputation until mouse release (`mouseReleaseEvent`), ensuring instant 60–144 FPS responsive dragging with atomic undo/redo history.
- **UI & Usability Enhancements**:
  - Added dedicated **"Open SVG File..."** button in the Project tab of the Left Sidebar.
  - Added **"Rename"** and **"Delete"** management buttons for custom machine profiles in Left Sidebar, protecting the default `Bambu Lab A1 Mini` from deletion.
  - Added empty-project warning dialogs preventing accidental export of empty SVGs, reports, or PNG previews.
  - Added direct keyboard shortcuts (`+`, `=`, `-`, `_`) for intuitive canvas zooming.
  - Dynamically enabled/disabled simulator playback transport controls and scrub slider based on toolpath availability.
  - Preserved proportional aspect ratio scaling during width/height spinbox modifications under arbitrary element rotations.

---

## [1.1.0] - 2026-10-30

### Added
- **Multiplatform Compatibility (Windows, Linux, macOS)**:
  - Added OS-agnostic path handling and user data directory detection (`app/core/platform_utils.py`).
  - Added native font fallbacks and theme consistency for Windows, Linux (Wayland & X11), and macOS (Retina High-DPI).
  - Added cross-platform build scripts: `build_linux.sh` and `build_macos.sh` (packaging `.app` and `.dmg`).
  - Added GitHub Actions CI/CD multiplatform matrix workflow (`.github/workflows/build_and_test.yml`) testing simultaneously on `windows-latest`, `ubuntu-latest`, and `macos-latest`.
- **Adversarial Fuzzing & QA Test Batteries**:
  - Added `tests/test_fuzzing.py`: testing corrupted XML, NaN/Infinity, extreme scientific notations, and singular matrices.
  - Added `tests/test_gcode_edge_cases.py`: testing zero-area pen clicks, micro-lines, 200 overlapping paths, F0 prevention, and soft-stop precision.
  - Added `tests/test_stress_concurrency.py`: simulator monkey testing, rapid resize, zoom/pan stress, Undo/Redo stack exhaustion, and QThreadPool task cancellation.
  - Comprehensive technical bug hunt report: `BUG_HUNT_LOG.md`.

### Fixed
- Fixed float infinity overflow (`OverflowError`) and `NaN` conversion crash in cubic Bézier Wang step calculation.
- Fixed unhandled XML syntax errors on empty, truncated, or corrupted files in `SvgParser`.
- Fixed dropped 1-point drawings, enabling zero-area isolated pen clicks (dots) with controlled dwell and pen transitions.
- Fixed zero/negative feedrate vulnerability ($F \le 0$) in G-code generator and added explicit safety inspection.
- Fixed unchecked negative $Z$ coordinates in the G-code validator stream.
- Tightened soft-stop boundary precision from $1e-4$ to $1e-5\text{ mm}$, guaranteeing strict mechanical enclosure.
- Fixed missing UI font helper methods on `BuildPlateCanvas` during paint events.
- Fixed modal import error dialog hanging headless test environments.
- Fixed orphan thread and dangling signal risk during window close by ensuring threadpool completion.
- Bounded `QUndoStack` to 300 entries to prevent memory exhaustion under heavy transform sequences.

---

## [1.0.0] - 2026-10-30

### Added
- **Native Graphical User Interface (PySide6)**:
  - Commercial CAD/CAM dark graphite engineering theme with responsive three-column layout.
  - Interactive top toolbar with project management, undo/redo, pen calibration, safety status, and quick export.
  - Left sidebar with tabbed navigation: Project/Layers, Machine Configuration, Pen Setup, and Export Settings.
  - Central 2D build plate workspace representing the Bambu Lab A1 Mini (180 × 180 mm).
  - Right inspector panel for real-time dimension editing, position adjustments, scaling, rotation, stroke/fill modes, and path optimization.
  - Bottom status bar providing real-time drawing statistics, path count, travel/draw distances, time estimation, and safety status.

- **SVG Parsing & Geometry Processing**:
  - Full vector primitive parsing: `<path>`, `<rect>`, `<circle>`, `<ellipse>`, `<line>`, `<polyline>`, `<polygon>`, and `<text>`/`<tspan>`.
  - Adaptive De Casteljau cubic and quadratic Bézier curve flattening.
  - High-precision W3C SVG 1.1 F.6 elliptical arc conversion and subdivision.
  - Homogeneous $3 \times 3$ affine transformation matrix composition for nested `<g>` and `<use>` elements (`matrix`, `translate`, `scale`, `rotate`, `skewX`, `skewY`).
  - Unit conversion engine supporting `mm`, `cm`, `in`, `pt`, `pc`, and `px` (96 DPI CSS/SVG2 standard).
  - Y-axis inversion mapping SVG top-left coordinates to printer front-left origin coordinates.
  - Transparent diagnostics reporting for non-vector or unsupported SVG tags (`<image>`, `<foreignObject>`, `<filter>`, etc.).

- **Shape Fill & Hatching Engine**:
  - Outline only mode.
  - Ignore fills mode.
  - Linear hatching pattern fill with configurable line spacing (`mm`) and angle (`°`).
  - Dual-angle cross-hatching with alternating scan directions to reduce travel overhead.
  - Concentric contour polygon offsetting via Shapely.

- **Toolpath Optimization**:
  - Four optimization strategies: Original SVG order, Direction Optimization, Nearest-Neighbor ordering, and Minimum Travel (Nearest-Neighbor + 2-Opt local search).
  - Path direction reversal optimization for open polylines.
  - Automatic endpoint joining within configurable threshold to eliminate unnecessary pen lifts.
  - Real-time travel distance savings calculation and percentage metric display.

- **Independent G-Code Generation & Bambu Lab Compatibility Layer**:
  - Generation of clean, human-readable, commented G-code (`G21`, `G90`, `G0`, `G1`, `G4`).
  - Three distinct workflow modes:
    - **A1 Mini Direct MicroSD Execution (`.gcode`)**: Cold-plotting safe start/end sequences (`M104 S0`, `M140 S0`, `M106 S0`, `G28` homing) tailored for direct selection on printer touchscreen.
    - **Bambu Studio Container (`.gcode.3mf`)**: Open Packaging Conventions archive bundling `Metadata/plate_1.gcode`, `plate_1.gcode.md5`, `slice_info.config`, `3dmodel.model`, and rendered PNG thumbnail.
    - **Standard Generic Plotter (`.gcode`)**: Raw machine-independent plotting G-code.

- **Interactive Build Plate Workspace & Tools**:
  - Dual millimeter rulers (top and left) with real-time cursor indicator lines.
  - Multi-tier grid (1 mm fine grid when zoomed, 10 mm minor, 30 mm major grid).
  - Configurable safety margin visualization and coordinate axes (`+X` / `+Y`).
  - Interactive selection and translation gizmo on the build plate with undo/redo integration.
  - Point-to-point measurement tool reporting $\Delta X$, $\Delta Y$, distance $D$ (`mm`), and angle ($^\circ$).
  - Pan and cursor-centered wheel zoom with HUD controls (`Zoom In`, `Zoom Out`, `Fit Plate`, `Grid Toggle`, `Travel Toggle`).

- **Live Toolpath Simulator**:
  - Real-time animated trajectory preview matching physical movement feed rates.
  - Transport controls: Play, Pause, Restart, Step Forward, Step Backward, and progress scrubber slider.
  - Adjustable playback speed from $0.25\times$ to $25\times$.
  - Progressive rendering differentiating executed, current, and upcoming toolpaths.
  - Live toolhead marker indicating **PEN UP** vs. **PEN DOWN** states and instantaneous $(X, Y, Z)$ coordinates.
  - Active G-code command and line number readout.

- **Mandatory Safety Validation Engine**:
  - Automated pre-export inspection checking machine volume ($0..180\text{ mm}$), safe Z boundaries, negative coordinates, and feed rates.
  - Pen state machine validation guaranteeing pen-down transitions before drawing moves and pen-up transitions before travel moves and job completion.
  - Command filtering blocking active heaters (`M109`, `M190`, `M104 > 0`, `M140 > 0`), extrusion (`E` axis moves), and unverified firmware calibration macros.
  - Multi-level classification: Valid, Warning, and Critical Error (blocking executable export on critical issues).
  - Detailed findings table reporting exact coordinates, line numbers, and responsible commands.

- **Hardware Profile & Calibration System**:
  - Built-in machine profile for Bambu Lab A1 Mini with configurable margins, offsets, and speed limits.
  - Built-in pen profiles: Fineliner (0.4mm), Ballpoint (0.7mm), Technical Pen (0.2mm), and Bold Marker (1.0mm).
  - Full CRUD for machine and pen profiles with JSON persistence.
  - Guided 6-Step Pen Calibration Wizard with Z contact measurement, safe lift height calculation, and calibration test pattern export.

- **Project Management & Exports**:
  - Project file format (`.a1plot` JSON) preserving artwork, placement, profiles, fill settings, and optimization parameters.
  - Autosave and crash recovery prompts on startup.
  - High-resolution build plate PNG export.
  - Optimized vector SVG export.
  - Comprehensive safety validation report export in Markdown and JSON formats.

- **Testing & Packaging**:
  - Comprehensive automated test suite (`pytest`) covering 20 test suites across geometry, units, transformations, optimization, safety rules, and UI integration.
  - Standalone Windows executable distribution built with PyInstaller (`dist/A1 Mini Pen Plotter/A1 Mini Pen Plotter.exe`).
  - Automated build script (`build_windows.bat`) handling virtualenv creation, test execution, PyInstaller packaging, and output verification.
  - User installation script (`scripts/install_windows.ps1`) and Inno Setup configuration (`scripts/installer.iss`).
