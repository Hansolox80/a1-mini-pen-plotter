"""Undo/Redo command stack implementations using QUndoCommand."""

from __future__ import annotations

from typing import Callable

from PySide6.QtGui import QUndoCommand

from app.core.models import DocumentTransform


class TransformChangeCommand(QUndoCommand):
    """Undoable command for changing DocumentTransform (position, scale, rotation, mirror)."""

    def __init__(
        self,
        old_transform: DocumentTransform,
        new_transform: DocumentTransform,
        apply_callback: Callable[[DocumentTransform], None],
        description: str = "Transform Drawing",
    ) -> None:
        super().__init__(description)
        self.old_transform = DocumentTransform.from_dict(old_transform.to_dict())
        self.new_transform = DocumentTransform.from_dict(new_transform.to_dict())
        self.apply_callback = apply_callback

    def undo(self) -> None:
        self.apply_callback(DocumentTransform.from_dict(self.old_transform.to_dict()))

    def redo(self) -> None:
        self.apply_callback(DocumentTransform.from_dict(self.new_transform.to_dict()))
