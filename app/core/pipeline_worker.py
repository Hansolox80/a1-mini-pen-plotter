"""Asynchronous background pipeline worker for non-blocking SVG parsing and toolpath generation."""

from __future__ import annotations

import logging
from typing import Any, Optional

from PySide6.QtCore import QObject, QRunnable, Signal

from app.core.coordinate_system import CoordinateTransformer
from app.core.gcode_generator import GcodeGenerator
from app.core.models import (
    BoundingBox,
    DocumentTransform,
    FillSettings,
    OptimizationSettings,
    ParsedSvgDocument,
    ToolpathMove,
    ToolpathStats,
    WorkflowMode,
)
from app.core.path_optimizer import ToolpathGenerator
from app.machine.a1_mini import MachineProfile
from app.machine.profiles import PenProfile
from app.machine.safety import SafetyValidationReport, SafetyValidator

logger = logging.getLogger(__name__)


class PipelineWorkerSignals(QObject):
    """Signals emitted by `PipelineWorker` across thread boundaries."""
    completed = Signal(int, dict)  # (task_id, result_dict)
    error = Signal(int, str)       # (task_id, error_message)


class PipelineWorker(QRunnable):
    """Executes heavy geometry transformation, hatching, 2-Opt toolpath optimization,

    G-code generation, and safety validation in a background QThreadPool thread to keep the UI at 60 FPS.
    """

    def __init__(
        self,
        task_id: int,
        doc: Optional[ParsedSvgDocument],
        doc_transform: DocumentTransform,
        machine: MachineProfile,
        pen: PenProfile,
        opt_settings: OptimizationSettings,
        fill_settings: FillSettings,
        workflow_mode: WorkflowMode,
        invert_y: bool = True,
        normalize_origin: bool = True,
        air_draw_mode: bool = False,
        air_draw_offset_z_mm: float = 15.0,
        project_name: str = "Untitled Plot",
    ) -> None:
        super().__init__()
        self.task_id = task_id
        self.doc = doc
        self.doc_transform = doc_transform
        self.machine = machine
        self.pen = pen
        self.opt_settings = opt_settings
        self.fill_settings = fill_settings
        self.workflow_mode = workflow_mode
        self.invert_y = invert_y
        self.normalize_origin = normalize_origin
        self.air_draw_mode = air_draw_mode
        self.air_draw_offset_z_mm = air_draw_offset_z_mm
        self.project_name = project_name

        self.signals = PipelineWorkerSignals()
        self._is_cancelled = False

    def cancel(self) -> None:
        self._is_cancelled = True

    def run(self) -> None:
        if self._is_cancelled:
            return

        try:
            if self.doc is None:
                empty_validation = SafetyValidator(self.machine, self.pen).validate([], "")
                self.signals.completed.emit(
                    self.task_id,
                    {
                        "transformed_elements": [],
                        "drawing_bounds": BoundingBox(0, 0, 0, 0),
                        "moves": [],
                        "stats": ToolpathStats(),
                        "gcode": "",
                        "validation": empty_validation,
                    },
                )
                return

            # 1. Transform elements to build plate space
            transformer = CoordinateTransformer(
                machine=self.machine,
                pen=self.pen,
                invert_y=self.invert_y,
                normalize_origin=self.normalize_origin,
            )
            transformed_elements = transformer.transform_document_elements(self.doc, self.doc_transform)
            drawing_bounds = transformer.compute_bounds(transformed_elements)

            if self._is_cancelled:
                return

            # 2. Generate toolpath moves & stats (includes hatching & path optimization)
            tp_gen = ToolpathGenerator(
                machine=self.machine,
                pen=self.pen,
                opt_settings=self.opt_settings,
                fill_settings=self.fill_settings,
                invert_y=self.invert_y,
                normalize_origin=self.normalize_origin,
                air_draw_mode=self.air_draw_mode,
                air_draw_offset_z_mm=self.air_draw_offset_z_mm,
            )
            moves, stats = tp_gen.generate(self.doc, self.doc_transform)

            if self._is_cancelled:
                return

            # 3. Generate G-code
            gcode_gen = GcodeGenerator(
                machine=self.machine,
                pen=self.pen,
                workflow_mode=self.workflow_mode,
            )
            gcode = gcode_gen.generate(moves, stats, project_name=self.project_name)

            if self._is_cancelled:
                return

            # 4. Mandatory Safety Validation
            validator = SafetyValidator(machine=self.machine, pen=self.pen)
            validation = validator.validate(moves, gcode)

            if self._is_cancelled:
                return

            # 5. Emit completed result
            self.signals.completed.emit(
                self.task_id,
                {
                    "transformed_elements": transformed_elements,
                    "drawing_bounds": drawing_bounds,
                    "moves": moves,
                    "stats": stats,
                    "gcode": gcode,
                    "validation": validation,
                },
            )

        except Exception as exc:
            logger.exception("Pipeline worker failed on task %d", self.task_id)
            self.signals.error.emit(self.task_id, str(exc))
