# Architecture & Bambu Lab A1 Mini G-Code Workflow

## 1. Modular Architecture

```text
A1-Mini-Pen-Plotter/
├── app/
│   ├── main.py                      # Application entry point, CLI flags, logging setup
│   ├── ui/
│   │   ├── main_window.py           # Main desktop shell, menu bar, toolbar, status bar, pipeline coordinator
│   │   ├── canvas.py                # 180x180mm interactive CAD build plate, rulers, grid, gizmos, simulator overlay
│   │   ├── theme.py                 # Three-layer design token system & dark engineering Qt Stylesheet (QSS)
│   │   ├── icons.py                 # Vector Lucide-style SVG icon renderer
│   │   ├── undo_commands.py         # QUndoCommand implementations for interactive transforms
│   │   ├── panels/
│   │   │   ├── left_sidebar.py      # Project, Layers, Machine Config, Pen Setup, and Export tabs
│   │   │   ├── right_inspector.py   # Dimensions, X/Y Position, Scale, Rotation, Fill & Optimization controls
│   │   │   └── simulator_bar.py     # Playback transport controls, speed selector, and live G-code readout
│   │   └── dialogs/
│   │       ├── calibration_wizard.py # 6-Step guided Pen Calibration Wizard
│   │       ├── validation_dialog.py  # Safety Validation Report & numbered G-code Viewer
│   │       └── settings_dialog.py    # Persistent application preferences window
│   ├── core/
│   │   ├── models.py                # Dataclasses for SVG elements, transforms, moves, and statistics
│   │   ├── svg_parser.py            # XML/SVG parser with affine matrices, viewBox, units, CSS, and text-to-path
│   │   ├── coordinate_system.py     # Y-axis inversion (SVG Y-down -> Printer Y-up) and plate-to-machine mapping
│   │   ├── geometry.py              # Adaptive Bézier/Arc flattening, Shapely hatching, and contour offsetting
│   │   ├── path_optimizer.py        # Nearest-Neighbor, 2-Opt local search, direction reversal, and path merging
│   │   ├── gcode_generator.py       # Independent G-code engine with workflow compatibility templates
│   │   └── simulator.py             # Time-interpolated trajectory playback state machine
│   ├── machine/
│   │   ├── a1_mini.py               # Bambu Lab A1 Mini hardware profile and cold-plotting G-code templates
│   │   ├── profiles.py              # Persistent JSON manager for Machine and Pen profiles
│   │   └── safety.py                # Mandatory validator blocking unsafe coordinates, speeds, and commands
│   ├── export/
│   │   ├── gcode_exporter.py        # .gcode, .gcode.3mf, optimized .svg, validation report, and PNG exporters
│   │   └── project_exporter.py      # .a1plot JSON project serialization, autosave, and crash recovery
│   └── resources/                   # Generated application logo.svg and multi-resolution icon.ico
├── profiles/                        # JSON machine and pen profile definitions
├── examples/                        # 11 test & sample SVGs + generated sample outputs
├── tests/                           # Automated pytest suite (engine + UI integration tests)
├── docs/                            # Screenshots and technical documentation
├── scripts/                         # Asset generator, screenshot helper, and Windows installer scripts
├── requirements.txt
├── A1_Mini_Pen_Plotter.spec
└── build_windows.bat
```

## 2. Coordinate Conversion Pipeline

1. **SVG Local Space → SVG Millimeter Space (`SvgParser`)**:
   - Evaluates root `width`, `height`, and `viewBox` (`preserveAspectRatio`) into a root $3 \times 3$ scaling matrix.
   - Accumulates nested `<g transform="...">` and element `transform` matrices via homogeneous matrix multiplication.
   - Flattens curves (`C`, `S`, `Q`, `T`, `A`, `<circle>`, `<ellipse>`, rounded `<rect>`) using adaptive local tolerance scaled by the inverse of the matrix singular value.
2. **SVG Millimeter Space (Y-Down) → Build Plate Space (Y-Up) (`CoordinateTransformer`)**:
   - Inverts the Y-axis ($y_{\text{plate}} = H_{\text{ref}} - y_{\text{svg}}$) so top-left SVG coordinates map accurately to front-left `(0,0)` build plate coordinates without mirroring the artwork.
   - Applies user scaling (`scale_x`, `scale_y`), mirroring (`mirror_x`, `mirror_y`), and rotation (`rotation_deg`) around the drawing center, then translates to `(pos_x_mm, pos_y_mm)`.
3. **Build Plate Space → Machine G-Code Space (`plate_to_machine_xy`)**:
   - Applies machine coordinate offsets (`coord_offset_x_mm`, `coord_offset_y_mm`) and active pen calibration offsets (`x_offset_mm`, `y_offset_mm`).
4. **Safety Verification (`SafetyValidator`)**:
   - Verifies every generated `ToolpathMove` and every line of the generated G-code before allowing executable export.
