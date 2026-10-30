"""Project file serialization (.a1plot JSON format), autosave, crash recovery, and recent projects manager."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
from pathlib import Path
from typing import Any, Optional

from app import __app_name__, __version__
from app.core.models import (
    DocumentTransform,
    FillSettings,
    OptimizationSettings,
    ParsedSvgDocument,
    SvgElement,
    SvgWarning,
    ToolpathMove,
    WorkflowMode,
)
from app.machine.a1_mini import MachineProfile, create_default_a1_mini_profile
from app.machine.profiles import PenProfile, create_default_pen_profiles


@dataclass
class PlotterProject:
    """Complete serializable state of an A1 Mini Pen Plotter project."""
    name: str = "Untitled Project"
    file_path: Optional[str] = None
    svg_document: Optional[ParsedSvgDocument] = None
    machine_profile: MachineProfile = field(default_factory=create_default_a1_mini_profile)
    pen_profile: PenProfile = field(default_factory=lambda: create_default_pen_profiles()[0])
    doc_transform: DocumentTransform = field(default_factory=DocumentTransform)
    fill_settings: FillSettings = field(default_factory=FillSettings)
    optimization_settings: OptimizationSettings = field(default_factory=OptimizationSettings)
    workflow_mode: WorkflowMode = WorkflowMode.BAMBU_SD_DIRECT
    invert_y: bool = True
    normalize_origin: bool = True
    air_draw_mode: bool = False
    air_draw_offset_z_mm: float = 15.0
    toolpath_moves: list[ToolpathMove] = field(default_factory=list)
    dirty: bool = False

    def to_dict(self) -> dict[str, Any]:
        svg_dict = None
        if self.svg_document is not None:
            svg_dict = {
                "file_path": self.svg_document.file_path,
                "width_mm": self.svg_document.width_mm,
                "height_mm": self.svg_document.height_mm,
                "viewbox": list(self.svg_document.viewbox) if self.svg_document.viewbox else None,
                "original_units": self.svg_document.original_units,
                "raw_svg_content": self.svg_document.raw_svg_content,
                "elements": [el.to_dict() for el in self.svg_document.elements],
                "warnings": [
                    {
                        "element_tag": w.element_tag,
                        "element_id": w.element_id,
                        "message": w.message,
                        "severity": w.severity,
                    }
                    for w in self.svg_document.warnings
                ],
            }

        return {
            "format": "a1_mini_pen_plotter_project",
            "version": __version__,
            "saved_at": datetime.now().isoformat(),
            "name": self.name,
            "workflow_mode": self.workflow_mode.value,
            "invert_y": self.invert_y,
            "normalize_origin": self.normalize_origin,
            "air_draw_mode": self.air_draw_mode,
            "air_draw_offset_z_mm": self.air_draw_offset_z_mm,
            "machine_profile": self.machine_profile.to_dict(),
            "pen_profile": self.pen_profile.to_dict(),
            "doc_transform": self.doc_transform.to_dict(),
            "fill_settings": self.fill_settings.to_dict(),
            "optimization_settings": self.optimization_settings.to_dict(),
            "svg_document": svg_dict,
            "toolpath_moves": [m.to_dict() for m in self.toolpath_moves],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], file_path: Optional[str] = None) -> PlotterProject:
        svg_data = data.get("svg_document")
        svg_doc: Optional[ParsedSvgDocument] = None
        if isinstance(svg_data, dict):
            vb = svg_data.get("viewbox")
            viewbox = (float(vb[0]), float(vb[1]), float(vb[2]), float(vb[3])) if vb and len(vb) == 4 else None
            elements = [SvgElement.from_dict(ed) for ed in svg_data.get("elements", [])]
            warnings = [
                SvgWarning(
                    element_tag=str(w.get("element_tag", "")),
                    element_id=str(w.get("element_id", "")),
                    message=str(w.get("message", "")),
                    severity=str(w.get("severity", "warning")),
                )
                for w in svg_data.get("warnings", [])
            ]
            svg_doc = ParsedSvgDocument(
                file_path=str(svg_data.get("file_path", "")),
                width_mm=float(svg_data.get("width_mm", 180.0)),
                height_mm=float(svg_data.get("height_mm", 180.0)),
                viewbox=viewbox,
                original_units=str(svg_data.get("original_units", "mm")),
                elements=elements,
                warnings=warnings,
                raw_svg_content=str(svg_data.get("raw_svg_content", "")),
            )

        wf_str = str(data.get("workflow_mode", WorkflowMode.BAMBU_SD_DIRECT.value))
        try:
            wf_mode = WorkflowMode(wf_str)
        except ValueError:
            wf_mode = WorkflowMode.BAMBU_SD_DIRECT

        moves = [ToolpathMove.from_dict(md) for md in data.get("toolpath_moves", [])]

        return cls(
            name=str(data.get("name", "Untitled Project")),
            file_path=file_path,
            svg_document=svg_doc,
            machine_profile=MachineProfile.from_dict(data.get("machine_profile", {})),
            pen_profile=PenProfile.from_dict(data.get("pen_profile", {})),
            doc_transform=DocumentTransform.from_dict(data.get("doc_transform", {})),
            fill_settings=FillSettings.from_dict(data.get("fill_settings", {})),
            optimization_settings=OptimizationSettings.from_dict(data.get("optimization_settings", {})),
            workflow_mode=wf_mode,
            invert_y=bool(data.get("invert_y", True)),
            normalize_origin=bool(data.get("normalize_origin", True)),
            air_draw_mode=bool(data.get("air_draw_mode", False)),
            air_draw_offset_z_mm=float(data.get("air_draw_offset_z_mm", 15.0)),
            toolpath_moves=moves,
            dirty=False,
        )


class ProjectManager:
    """Handles saving, loading, autosaving, crash recovery, and recent project tracking."""

    def __init__(self, app_data_dir: Optional[Path] = None) -> None:
        if app_data_dir is None:
            app_data_dir = Path.home() / ".a1_mini_pen_plotter"
        self.app_data_dir = Path(app_data_dir)
        self.app_data_dir.mkdir(parents=True, exist_ok=True)
        self.autosave_path = self.app_data_dir / "autosave_recovery.a1plot"
        self.recent_file_path = self.app_data_dir / "recent_projects.json"

    def save_project(self, project: PlotterProject, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        project.file_path = str(target.resolve())
        if project.name == "Untitled Project":
            project.name = target.stem
        target.write_text(json.dumps(project.to_dict(), indent=2), encoding="utf-8")
        project.dirty = False
        self.add_recent_project(str(target.resolve()))
        self.clear_autosave()

    def load_project(self, path: str | Path) -> PlotterProject:
        target = Path(path)
        data = json.loads(target.read_text(encoding="utf-8"))
        proj = PlotterProject.from_dict(data, file_path=str(target.resolve()))
        self.add_recent_project(str(target.resolve()))
        return proj

    def write_autosave(self, project: PlotterProject) -> None:
        try:
            self.autosave_path.write_text(json.dumps(project.to_dict(), indent=2), encoding="utf-8")
        except Exception:
            pass

    def has_recovery_file(self) -> bool:
        return self.autosave_path.exists() and self.autosave_path.stat().st_size > 10

    def load_recovery_project(self) -> Optional[PlotterProject]:
        if not self.has_recovery_file():
            return None
        try:
            data = json.loads(self.autosave_path.read_text(encoding="utf-8"))
            proj = PlotterProject.from_dict(data, file_path=None)
            proj.dirty = True
            return proj
        except Exception:
            return None

    def clear_autosave(self) -> None:
        try:
            if self.autosave_path.exists():
                self.autosave_path.unlink()
        except Exception:
            pass

    def get_recent_projects(self) -> list[str]:
        if not self.recent_file_path.exists():
            return []
        try:
            items = json.loads(self.recent_file_path.read_text(encoding="utf-8"))
            if isinstance(items, list):
                return [str(p) for p in items if Path(str(p)).exists()][:10]
        except Exception:
            pass
        return []

    def add_recent_project(self, file_path: str) -> None:
        recents = self.get_recent_projects()
        norm = str(Path(file_path).resolve())
        recents = [p for p in recents if p != norm]
        recents.insert(0, norm)
        try:
            self.recent_file_path.write_text(json.dumps(recents[:10], indent=2), encoding="utf-8")
        except Exception:
            pass
