"""Exporters for G-code (.gcode), Bambu Studio (.gcode.3mf), Optimized SVG (.svg), Validation Reports, and Preview PNGs."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from typing import Optional
import zipfile

from PIL import Image, ImageDraw

from app import __app_name__, __version__
from app.core.models import MovementType, ToolpathMove, ToolpathStats
from app.machine.a1_mini import MachineProfile
from app.machine.profiles import PenProfile
from app.machine.safety import SafetyValidationReport, SafetyValidator


class SafetyExportBlockedError(RuntimeError):
    """Raised when attempting to export an execution-ready file that contains Critical safety errors."""

    def __init__(self, message: str, report: SafetyValidationReport) -> None:
        super().__init__(message)
        self.report = report


def render_toolpath_preview_png_bytes(
    moves: list[ToolpathMove],
    machine: MachineProfile,
    width_px: int = 800,
    height_px: int = 800,
    show_travel: bool = True,
) -> bytes:
    """Renders a high-contrast top-down preview PNG of the build plate and generated toolpaths."""
    img = Image.new("RGBA", (width_px, height_px), (17, 19, 21, 255))
    draw = ImageDraw.Draw(img)

    pad = 48
    usable_w_px = width_px - 2 * pad
    usable_h_px = height_px - 2 * pad

    scale_x = usable_w_px / max(1.0, machine.nominal_x_mm)
    scale_y = usable_h_px / max(1.0, machine.nominal_y_mm)
    scale = min(scale_x, scale_y)

    def mm_to_px(mx: float, my: float) -> tuple[float, float]:
        px = pad + mx * scale
        # Build plate Y=0 is at the bottom (front), Y=180 is at the top (back)
        py = height_px - pad - my * scale
        return (px, py)

    # Draw build plate boundary
    x0, y0 = mm_to_px(0.0, machine.nominal_y_mm)
    x1, y1 = mm_to_px(machine.nominal_x_mm, 0.0)
    draw.rectangle([x0, y0, x1, y1], fill=(24, 27, 31, 255), outline=(65, 72, 84, 255), width=2)

    # Draw grid lines (every 10mm minor, 30mm major)
    step = 10
    while step < int(machine.nominal_x_mm):
        gx0, gy0 = mm_to_px(float(step), 0.0)
        gx1, gy1 = mm_to_px(float(step), machine.nominal_y_mm)
        col = (45, 50, 58, 255) if step % 30 == 0 else (32, 36, 42, 255)
        draw.line([(gx0, gy0), (gx1, gy1)], fill=col, width=1)
        step += 10

    step = 10
    while step < int(machine.nominal_y_mm):
        gx0, gy0 = mm_to_px(0.0, float(step))
        gx1, gy1 = mm_to_px(machine.nominal_x_mm, float(step))
        col = (45, 50, 58, 255) if step % 30 == 0 else (32, 36, 42, 255)
        draw.line([(gx0, gy0), (gx1, gy1)], fill=col, width=1)
        step += 10

    # Draw safety margin rectangle
    sx0, sy0 = mm_to_px(machine.usable_min_x, machine.usable_max_y)
    sx1, sy1 = mm_to_px(machine.usable_max_x, machine.usable_min_y)
    draw.rectangle([sx0, sy0, sx1, sy1], outline=(245, 158, 11, 140), width=1)

    # Draw travel moves first
    if show_travel:
        for mv in moves:
            if mv.move_type == MovementType.TRAVEL:
                p0 = mm_to_px(mv.start_x, mv.start_y)
                p1 = mm_to_px(mv.end_x, mv.end_y)
                draw.line([p0, p1], fill=(56, 189, 248, 110), width=1)

    # Draw pen-down drawing moves
    for mv in moves:
        if mv.move_type == MovementType.DRAW:
            p0 = mm_to_px(mv.start_x, mv.start_y)
            p1 = mm_to_px(mv.end_x, mv.end_y)
            draw.line([p0, p1], fill=(34, 197, 94, 255), width=2)

    # Draw origin marker (0,0)
    ox, oy = mm_to_px(0.0, 0.0)
    draw.ellipse([ox - 5, oy - 5, ox + 5, oy + 5], fill=(239, 68, 68, 255))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class GcodeExporter:
    """Exports validated G-code, Bambu Studio .gcode.3mf containers, Optimized SVGs, Reports, and Previews."""

    @staticmethod
    def export_gcode_file(
        output_path: str | Path,
        moves: list[ToolpathMove],
        gcode_text: str,
        machine: MachineProfile,
        pen: PenProfile,
    ) -> SafetyValidationReport:
        """Validates safety and writes execution-ready `.gcode` file. Blocks on Critical errors."""
        validator = SafetyValidator(machine=machine, pen=pen)
        report = validator.validate(moves=moves, gcode_text=gcode_text)
        if not report.can_export_executable:
            crit_titles = ", ".join(
                f"[{i.code}] {i.title}" for i in report.issues if i.severity.value == "critical"
            )
            raise SafetyExportBlockedError(
                f"Export blocked by {report.critical_count} critical safety validation error(s): {crit_titles}",
                report=report,
            )

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(gcode_text, encoding="utf-8")
        return report

    @staticmethod
    def export_bambu_3mf_file(
        output_path: str | Path,
        moves: list[ToolpathMove],
        gcode_text: str,
        stats: ToolpathStats,
        machine: MachineProfile,
        pen: PenProfile,
    ) -> SafetyValidationReport:
        """Validates and packages G-code into a Bambu Studio compatible `.gcode.3mf` container."""
        validator = SafetyValidator(machine=machine, pen=pen)
        report = validator.validate(moves=moves, gcode_text=gcode_text)
        if not report.can_export_executable:
            crit_titles = ", ".join(
                f"[{i.code}] {i.title}" for i in report.issues if i.severity.value == "critical"
            )
            raise SafetyExportBlockedError(
                f"3MF Export blocked by {report.critical_count} critical safety error(s): {crit_titles}",
                report=report,
            )

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        gcode_bytes = gcode_text.encode("utf-8")
        md5_hex = hashlib.md5(gcode_bytes).hexdigest().upper()
        png_bytes = render_toolpath_preview_png_bytes(moves, machine, width_px=512, height_px=512)

        content_types_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
  <Default Extension="png" ContentType="image/png"/>
  <Default Extension="gcode" ContentType="text/x.gcode"/>
  <Default Extension="config" ContentType="text/xml"/>
  <Default Extension="md5" ContentType="text/plain"/>
</Types>
"""
        rels_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Target="/3D/3dmodel.model" Id="rel-1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
  <Relationship Target="/Metadata/plate_1.png" Id="rel-2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/thumbnail"/>
</Relationships>
"""
        model_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" xmlns:BambuStudio="http://schemas.bambulab.com/package/2021">
  <metadata name="Application">{__app_name__} v{__version__}</metadata>
  <metadata name="BambuStudio:3mfVersion">1</metadata>
  <resources/>
  <build/>
</model>
"""
        est_secs = max(1, int(round(stats.estimated_time_seconds)))
        slice_info_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<config>
  <header>
    <header_item key="X-BBL-Client-Type" value="slicer"/>
    <header_item key="X-BBL-Client-Version" value="01.09.00.00"/>
  </header>
  <plate>
    <metadata key="index" value="1"/>
    <metadata key="printer_model_id" value="N1"/>
    <metadata key="nozzle_diameters" value="{pen.tip_diameter_mm:.2f}"/>
    <metadata key="gcode_file" value="Metadata/plate_1.gcode"/>
    <metadata key="thumbnail_file" value="Metadata/plate_1.png"/>
    <metadata key="prediction" value="{est_secs}"/>
    <metadata key="weight" value="0.0"/>
  </plate>
</config>
"""

        with zipfile.ZipFile(path, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("[Content_Types].xml", content_types_xml)
            zf.writestr("_rels/.rels", rels_xml)
            zf.writestr("3D/3dmodel.model", model_xml)
            zf.writestr("Metadata/plate_1.gcode", gcode_bytes)
            zf.writestr("Metadata/plate_1.gcode.md5", md5_hex + "\n")
            zf.writestr("Metadata/slice_info.config", slice_info_xml)
            zf.writestr("Metadata/plate_1.png", png_bytes)

        return report

    @staticmethod
    def export_optimized_svg(
        output_path: str | Path,
        moves: list[ToolpathMove],
        machine: MachineProfile,
        pen: PenProfile,
    ) -> None:
        """Exports the optimized toolpath trajectories back into a clean, physical-millimeter SVG file."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        w = machine.nominal_x_mm
        h = machine.nominal_y_mm

        polylines: list[list[tuple[float, float]]] = []
        current_poly: list[tuple[float, float]] = []

        for mv in moves:
            if mv.move_type == MovementType.DRAW:
                # Convert from machine Y-up back to SVG Y-down
                sx, sy = mv.start_x, h - mv.start_y
                ex, ey = mv.end_x, h - mv.end_y
                if not current_poly:
                    current_poly = [(sx, sy), (ex, ey)]
                else:
                    current_poly.append((ex, ey))
            else:
                if len(current_poly) >= 2:
                    polylines.append(current_poly)
                current_poly = []

        if len(current_poly) >= 2:
            polylines.append(current_poly)

        svg_lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.2f}mm" height="{h:.2f}mm" viewBox="0 0 {w:.2f} {h:.2f}">',
            f'  <!-- Exported by {__app_name__} v{__version__} | Ordered Paths: {len(polylines)} -->',
            f'  <g id="optimized_toolpath" fill="none" stroke="{pen.color_hex}" stroke-width="{pen.tip_diameter_mm:.2f}" stroke-linecap="round" stroke-linejoin="round">',
        ]
        for idx, poly in enumerate(polylines, start=1):
            d_parts = [f"M {poly[0][0]:.3f} {poly[0][1]:.3f}"]
            for pt in poly[1:]:
                d_parts.append(f"L {pt[0]:.3f} {pt[1]:.3f}")
            svg_lines.append(f'    <path id="opt_path_{idx}" d="{" ".join(d_parts)}" />')

        svg_lines.append("  </g>")
        svg_lines.append("</svg>\n")
        path.write_text("\n".join(svg_lines), encoding="utf-8")

    @staticmethod
    def export_validation_report(
        output_path: str | Path,
        report: SafetyValidationReport,
        machine: MachineProfile,
        pen: PenProfile,
        stats: Optional[ToolpathStats] = None,
    ) -> None:
        """Exports the safety validation report as JSON or formatted Markdown/Text."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = report.to_dict()
        payload["machine_profile"] = machine.name
        payload["pen_profile"] = pen.name
        if stats:
            payload["toolpath_stats"] = stats.to_dict()

        if path.suffix.lower() == ".json":
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        else:
            lines = [
                f"# {__app_name__} — Safety Validation Report",
                f"Overall Status: {report.overall_status.value.upper()}",
                f"Executable Export Allowed: {'YES' if report.can_export_executable else 'NO (BLOCKED)'}",
                f"Machine Profile: {machine.name} ({machine.nominal_x_mm:.0f}x{machine.nominal_y_mm:.0f} mm)",
                f"Pen Profile: {pen.name} (Draw Z={pen.drawing_z_mm:.2f} mm, Pen-Up Z={pen.pen_up_z_mm:.2f} mm)",
                f"Checked Movements: {report.checked_movements} | Checked G-code Lines: {report.checked_gcode_lines}",
                f"Coordinate Bounds: X[{report.min_x_found:.2f}..{report.max_x_found:.2f}] "
                f"Y[{report.min_y_found:.2f}..{report.max_y_found:.2f}] Z[{report.min_z_found:.2f}..{report.max_z_found:.2f}] mm",
                "",
                "## Mandatory Physical Collision-Risk Warnings",
            ]
            for cw in report.collision_risk_warnings:
                lines.append(f"- [COLLISION RISK] {cw}")
            lines.append("")
            lines.append(f"## Validation Findings ({len(report.issues)} total)")
            if not report.issues:
                lines.append("- No validation issues detected.")
            else:
                for iss in report.issues:
                    coord_str = (
                        f" @ ({iss.coordinates[0]:.2f}, {iss.coordinates[1]:.2f}, {iss.coordinates[2]:.2f}) mm"
                        if iss.coordinates
                        else ""
                    )
                    line_str = f" [Line {iss.line_number}]" if iss.line_number else ""
                    cmd_str = f" | Cmd: `{iss.command}`" if iss.command else ""
                    lines.append(
                        f"- [{iss.severity.value.upper()}] {iss.code}: {iss.title}{line_str}{coord_str}{cmd_str}\n"
                        f"  {iss.message}"
                    )
            lines.append("")
            lines.append("## Disclaimer")
            lines.append(report.disclaimer)
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    @staticmethod
    def export_preview_image(
        output_path: str | Path,
        moves: list[ToolpathMove],
        machine: MachineProfile,
        width_px: int = 1200,
        height_px: int = 1200,
    ) -> None:
        """Exports a high-resolution PNG preview of the build plate and toolpaths."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        png_bytes = render_toolpath_preview_png_bytes(moves, machine, width_px=width_px, height_px=height_px)
        path.write_bytes(png_bytes)
