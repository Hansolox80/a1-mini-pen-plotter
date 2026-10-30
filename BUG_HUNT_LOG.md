# Bug Hunt & Security Hardening Report: A1 Mini Pen Plotter

**Role**: Senior QA & Software Security Engineer  
**Date**: October 2026  
**Status**: 100% Passed (42/42 Automated Tests Passing, 0 Errors, 0 Warnings)  
**Target Architecture**: Windows, Linux, macOS | Bambu Lab A1 Mini Pen Plotter  

---

## Executive Summary

An exhaustive round of stress testing, adversarial fuzzing, and mechanical safety validation was conducted on the **A1 Mini Pen Plotter** desktop application. The system was systematically subjected to corrupted files, numerical singularities, mechanical limit violations, high-concurrency UI monkey testing, and abrupt lifecycle interruptions.

All identified vulnerabilities (12 distinct bugs across arithmetic, geometric, G-code validation, concurrency, and UI layers) have been investigated, isolated, resolved at the root cause, and permanently covered with automated regression tests in `pytest`.

```
============================= Test Session Summary =============================
tests/test_engine.py             24 PASSED   (Core geometry, transforms, safety)
tests/test_fuzzing.py             5 PASSED   (Adversarial SVGs, singularities, NaN/Inf)
tests/test_gcode_edge_cases.py    6 PASSED   (Zero-area, micro-lines, soft-stop, F0)
tests/test_stress_concurrency.py  5 PASSED   (Monkey testing, zoom/pan, Undo/Redo)
tests/test_ui.py                  2 PASSED   (MainWindow, dialogs, pipeline)
--------------------------------------------------------------------------------
TOTAL: 42 passed in 12.61s (100% success rate)
================================================================================
```

---

## Detailed Vulnerability & Bug Hunt Registry

### 1. Arithmetic & Geometry Engine

#### BUG-001: Float Infinity Overflow in Wang's Bézier Subdivision Step Calculation
- **Severity**: Critical (Application Crash / Unhandled Exception)
- **Component**: [`app.core.geometry.flatten_cubic_bezier`](file:///d:/Antigravity%20Projetos/Software/A1%20Mini%20Pen%20Plotter/app/core/geometry.py)
- **Root Cause**: When evaluating Bézier curves with extreme coordinate scales or huge second-derivative norms ($max\_d \to \infty$, e.g., $10^{200}$), NumPy's norm calculation produced `float('inf')`. Subsequent evaluation of `int(np.ceil(np.sqrt((3.0 * max_d) / (4.0 * tol))))` raised `OverflowError: cannot convert float infinity to integer`.
- **Remediation**: Control points are defensively clamped and checked with `math.isfinite`. Wang's subdivision calculation is guarded with `try / except (OverflowError, ValueError)` and bounded strictly to $[2, 64]$ steps.
- **Automated Regression Test**: `tests/test_fuzzing.py::test_fuzz_degenerate_beziers`

#### BUG-002: NaN Float-to-Integer Conversion Failure in Bézier Flattening
- **Severity**: Critical (Application Crash)
- **Component**: [`app.core.geometry.flatten_cubic_bezier`](file:///d:/Antigravity%20Projetos/Software/A1%20Mini%20Pen%20Plotter/app/core/geometry.py)
- **Root Cause**: Supplying `NaN` coordinates in `<path d="...">` caused $max\_d$ to evaluate to `nan`. Python's `int(np.nan)` immediately raised `ValueError: cannot convert float NaN to integer`.
- **Remediation**: Added upfront sanitization of control point coordinates. If any coordinate is non-finite, endpoints are safely sanitized to finite coordinates. Flattened output points are filtered to guarantee strict finiteness.
- **Automated Regression Test**: `tests/test_fuzzing.py::test_fuzz_degenerate_beziers`

#### BUG-003: Arc Singularities and Negative Radii Math Domain Errors
- **Severity**: High (Arithmetic Exception)
- **Component**: [`app.core.geometry.flatten_svg_arc`](file:///d:/Antigravity%20Projetos/Software/A1%20Mini%20Pen Plotter/app/core/geometry.py)
- **Root Cause**: SVG arcs with $r_x \le 0, r_y \le 0$, non-finite rotation angles, or coincident start/end points caused zero-division in center parameterization and negative values inside `math.sqrt()` or `math.acos()`.
- **Remediation**: `rx` and `ry` are forced to positive values via `abs()`. Radii $< 10^{-9}$ or $> 10^{12}$ immediately collapse to straight segment $[p_0, p_1]$. Angular ratios inside `math.acos()` are clamped to $[-1.0, 1.0]$, and step counts are bounded to $[4, 128]$.
- **Automated Regression Test**: `tests/test_fuzzing.py::test_fuzz_degenerate_arcs`

---

### 2. SVG Parser & Adversarial Input Robustness

#### BUG-004: Unhandled XML Syntax and Truncation Errors
- **Severity**: Critical (Parser Crash)
- **Component**: [`app.core.svg_parser.SvgParser`](file:///d:/Antigravity%20Projetos/Software/A1%20Mini%20Pen%20Plotter/app/core/svg_parser.py)
- **Root Cause**: Passing empty files, plain text, unclosed tags, or binary files to `parse_string` or `parse_file` raised uncaught `ET.ParseError` or `DefusedXmlException`.
- **Remediation**: Wrapped XML parsing in comprehensive exception handling. On syntax errors or missing files, `SvgParser` returns a valid `ParsedSvgDocument` with zero elements and a structured `SvgWarning(severity="critical", message=...)`, preventing any crash.
- **Automated Regression Test**: `tests/test_fuzzing.py::test_fuzz_corrupted_xml_and_empty_inputs`

#### BUG-005: Singular Affine Transformation Matrices ($\det = 0$) and Astronomical Scales
- **Severity**: High (Geometric Degeneracy)
- **Component**: [`app.core.svg_parser.parse_transform_matrix`](file:///d:/Antigravity%20Projetos/Software/A1%20Mini%20Pen%20Plotter/app/core/svg_parser.py)
- **Root Cause**: Singular transform matrices (`matrix(0 0 0 0 0 0)`, `scale(0 0)`) or extreme shears (`skewX(90)` where $\tan(90^\circ) \to \infty$) generated infinite/NaN coordinates during matrix multiplication.
- **Remediation**: Clamped trigonometric shear factors to $[-10^6, 10^6]$. Checked `np.all(np.isfinite(res))` before matrix assignment. `apply_matrix_to_polyline` filters output points to finite coordinates within physical boundaries ($|x|, |y| < 10^7\text{ mm}$).
- **Automated Regression Test**: `tests/test_fuzzing.py::test_fuzz_singular_and_extreme_transforms`

---

### 3. Mechanical Safety & G-Code Edge Cases

#### BUG-006: Silently Dropped Zero-Area Drawings and Isolated Pen Clicks
- **Severity**: High (Functional Defect & Incorrect Bounds)
- **Component**: [`app.core.path_optimizer.ToolpathGenerator`](file:///d:/Antigravity%20Projetos/Software/A1%20Mini%20Pen%20Plotter/app/core/path_optimizer.py) & [`app.core.svg_parser.parse_svg_path_d`](file:///d:/Antigravity%20Projetos/Software/A1%20Mini%20Pen%20Plotter/app/core/svg_parser.py)
- **Root Cause**: Hardcoded checks `if len(current_poly) >= 2` and `if len(cleaned) < 2: continue` discarded 1-point paths (such as `M 50 50` or zero-radius circles). Furthermore, toolpath bounding boxes failed to update for point clicks.
- **Remediation**: Allowed single-point polylines (`len >= 1`). Single points generate atomic sequence: `TRAVEL` $\to$ `PEN_DOWN` (with dwell stabilization) $\to$ `PEN_UP`. Bounds tracking initializes with `sx, sy` for every path.
- **Automated Regression Test**: `tests/test_gcode_edge_cases.py::test_zero_area_drawing_point_clicks`

#### BUG-007: Zero and Negative Feedrate ($F \le 0$) Generation and Inspection Gap
- **Severity**: Critical (Printer Firmware Stall / Motion Freeze)
- **Component**: [`app.core.gcode_generator.GcodeGenerator`](file:///d:/Antigravity%20Projetos/Software/A1%20Mini%20Pen%20Plotter/app/core/gcode_generator.py) & [`app.machine.safety.SafetyValidator`](file:///d:/Antigravity%20Projetos/Software/A1%20Mini%20Pen%20Plotter/app/machine/safety.py)
- **Root Cause**: Neither G-code generator nor safety validator checked for $F \le 0$. A zero feedrate produces `F0`, causing firmware command rejection or motion freeze.
- **Remediation**: `GcodeGenerator` clamps all movement feedrates to $\ge 60\text{ mm/min}$ ($1\text{ mm/s}$). `SafetyValidator` flags any $F \le 0$ movement or G-code parameter as a `CRITICAL` issue (`ZERO_OR_NEGATIVE_FEEDRATE`).
- **Automated Regression Test**: `tests/test_gcode_edge_cases.py::test_feedrate_zero_and_negative_feedrate_prevention`

#### BUG-008: Missing Negative Z Inspection in G-Code Parser
- **Severity**: Critical (Mechanical Bed Crash)
- **Component**: [`app.machine.safety.SafetyValidator._validate_gcode_lines`](file:///d:/Antigravity%20Projetos/Software/A1%20Mini%20Pen%20Plotter/app/machine/safety.py)
- **Root Cause**: The raw G-code inspector checked `if cur_x < -1e-4 or cur_y < -1e-4:`, omitting `cur_z`. A command like `G1 Z-5.0` was not flagged as `GCODE_NEGATIVE_COORDINATE`.
- **Remediation**: Included `cur_z < -1e-4` in the coordinate check, blocking any negative Z command in the G-code stream.
- **Automated Regression Test**: `tests/test_gcode_edge_cases.py::test_negative_z_and_final_pen_lift_enforcement`

#### BUG-009: Soft-Stop Floating-Point Precision Vulnerability ($0.0001\text{ mm}$)
- **Severity**: Medium (Safety Margin Escape)
- **Component**: [`app.machine.safety.SafetyValidator`](file:///d:/Antigravity%20Projetos/Software/A1%20Mini%20Pen%20Plotter/app/machine/safety.py)
- **Root Cause**: An epsilon tolerance of $1e-4$ allowed a movement targeting $180.0001\text{ mm}$ to escape boundary detection.
- **Remediation**: Tightened comparison threshold to $1e-5\text{ mm}$ ($10\text{ nm}$), ensuring that exact machine limits ($180.0000$) pass cleanly while any overflow ($180.0001$) is strictly blocked as `OUTSIDE_MACHINE_BOUNDS`.
- **Automated Regression Test**: `tests/test_gcode_edge_cases.py::test_boundary_precision_soft_stop`

#### BUG-010: Missing Final Pen Lift Verification in G-Code Program
- **Severity**: High (Paper Tearing / Toolhead Drag)
- **Component**: [`app.machine.safety.SafetyValidator._validate_gcode_lines`](file:///d:/Antigravity%20Projetos/Software/A1%20Mini%20Pen%20Plotter/app/machine/safety.py)
- **Root Cause**: G-code validation did not verify that the final toolhead position left the pen lifted to at least `pen_up_z`.
- **Remediation**: Added post-loop validation asserting `cur_z >= self.pen.pen_up_z_mm - 0.05` at the end of the G-code program.
- **Automated Regression Test**: `tests/test_gcode_edge_cases.py::test_negative_z_and_final_pen_lift_enforcement`

---

### 4. UI Stability, Concurrency & Concurrency Lifecycle

#### BUG-011: Missing Font Factory Method on Canvas View
- **Severity**: Medium (GUI Paint Event Crash)
- **Component**: [`app.ui.canvas.BuildPlateCanvas`](file:///d:/Antigravity%20Projetos/Software/A1%20Mini%20Pen%20Plotter/app/ui/canvas.py)
- **Root Cause**: Paint routines called `self._make_ui_font(...)` and `self._make_mono_font(...)` which were not defined as methods on `BuildPlateCanvas`.
- **Remediation**: Implemented `_make_mono_font` and `_make_ui_font` using platform-agnostic font resolution (`get_mono_font_family()` and `get_system_font_family()`).
- **Automated Regression Test**: `tests/test_stress_concurrency.py::test_canvas_frenetic_zoom_pan_and_tools`

#### BUG-012: Orphan Threads and Dangling Signal Risk on Window Close
- **Severity**: High (Process Shutdown Segfault / Race Condition)
- **Component**: [`app.ui.main_window.MainWindow.closeEvent`](file:///d:/Antigravity%20Projetos/Software/A1%20Mini%20Pen%20Plotter/app/ui/main_window.py)
- **Root Cause**: Closing the main window while a background worker was computing toolpaths in `QThreadPool` allowed the worker to emit signals on closing/destroyed QObjects.
- **Remediation**: Updated `closeEvent` to cancel `_active_worker`, stop `autosave_timer` and `simulator_bar.timer`, and wait on `thread_pool.waitForDone(300)`.
- **Automated Regression Test**: `tests/test_stress_concurrency.py::test_qthreadpool_rapid_task_cancellation_and_file_switching`

#### BUG-013: Unbounded Memory Growth in Transform Undo Stack
- **Severity**: Low (Memory Footprint)
- **Component**: [`app.ui.main_window.MainWindow.__init__`](file:///d:/Antigravity%20Projetos/Software/A1%20Mini%20Pen%20Plotter/app/ui/main_window.py)
- **Root Cause**: `QUndoStack` had no upper limit ($0 = \infty$), allowing hundreds of consecutive transforms to consume unbounded memory.
- **Remediation**: Set `self.undo_stack.setUndoLimit(300)`.
- **Automated Regression Test**: `tests/test_stress_concurrency.py::test_undo_redo_stack_exhaustion`

---

## Verification Matrix

| Test Suite | Tests | Status | Focus Areas |
| :--- | :---: | :---: | :--- |
| `tests/test_engine.py` | 24 | **PASSED** | 20x20mm exact dimensions, arcs/Béziers, Hatching, 2-Opt TSP, SD/Bambu G-code, Air Draw |
| `tests/test_fuzzing.py` | 5 | **PASSED** | Corrupted XML, NaN/Infinity coordinates, degenerate curves, singular matrices |
| `tests/test_gcode_edge_cases.py` | 6 | **PASSED** | Zero-area pen clicks, micro-lines, 200 overlaps, soft-stop precision, F0/Z<0 safety |
| `tests/test_stress_concurrency.py` | 5 | **PASSED** | Transport monkey testing, zoom/pan stress, rapid resizing, Undo/Redo exhaustion, QThreadPool cancellation |
| `tests/test_ui.py` | 2 | **PASSED** | Full startup pipeline, Pen Calibration Wizard, Safety Inspector, Settings |
| **Total** | **42** | **100% OK** | Complete non-regression coverage |
