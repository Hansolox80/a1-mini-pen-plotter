"""Safety Validation & G-code Inspector Dialog (Section 10)."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.machine.safety import SafetyValidationReport, ValidationSeverity


class ValidationAndGcodeDialog(QDialog):
    """Displays mandatory safety validation findings, collision-risk warnings, and complete G-code listing."""

    def __init__(
        self,
        report: SafetyValidationReport,
        gcode_text: str,
        initial_tab: int = 0,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Safety Validation & G-Code Inspector")
        self.resize(860, 600)

        self.report = report
        self.gcode_text = gcode_text

        self._build_ui(initial_tab)

    def _build_ui(self, initial_tab: int) -> None:
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(14, 14, 14, 14)
        vbox.setSpacing(10)

        # Status Banner
        banner = QFrame(self)
        banner.setObjectName("SectionCard")
        b_layout = QHBoxLayout(banner)
        b_layout.setContentsMargins(12, 10, 12, 10)

        status = self.report.overall_status
        if status == ValidationSeverity.CRITICAL:
            badge_text = f"CRITICAL ERROR ({self.report.critical_count}) — EXECUTABLE EXPORT BLOCKED"
            badge_style = "color: #FCA5A5; background-color: rgba(239, 68, 68, 0.2); border: 1px solid #EF4444; padding: 4px 10px; border-radius: 4px; font-weight: 700;"
        elif status == ValidationSeverity.WARNING:
            badge_text = f"WARNING ({self.report.warning_count}) — EXPORT PERMITTED AFTER REVIEW"
            badge_style = "color: #FDE68A; background-color: rgba(245, 158, 11, 0.2); border: 1px solid #F59E0B; padding: 4px 10px; border-radius: 4px; font-weight: 700;"
        else:
            badge_text = "VALID — ALL COORDINATE & COMMAND CHECKS PASSED"
            badge_style = "color: #4ADE80; background-color: rgba(34, 197, 94, 0.2); border: 1px solid #22C55E; padding: 4px 10px; border-radius: 4px; font-weight: 700;"

        lbl_badge = QLabel(badge_text, banner)
        lbl_badge.setStyleSheet(badge_style)
        b_layout.addWidget(lbl_badge)
        b_layout.addStretch(1)

        lbl_stats = QLabel(
            f"Checked {self.report.checked_movements} moves  |  {self.report.checked_gcode_lines} G-code lines",
            banner,
        )
        lbl_stats.setObjectName("MonoValueLabel")
        b_layout.addWidget(lbl_stats)
        vbox.addWidget(banner)

        tabs = QTabWidget(self)
        tabs.addTab(self._build_validation_tab(), "Safety Validation Report")
        tabs.addTab(self._build_gcode_tab(), "Generated G-Code Program")
        tabs.setCurrentIndex(initial_tab)
        vbox.addWidget(tabs, 1)

        footer = QHBoxLayout()
        lbl_disc = QLabel(self.report.disclaimer, self)
        lbl_disc.setObjectName("MutedLabel")
        lbl_disc.setWordWrap(True)
        footer.addWidget(lbl_disc, 1)

        btn_close = QPushButton("Close", self)
        btn_close.setObjectName("PrimaryButton")
        btn_close.clicked.connect(self.accept)
        footer.addWidget(btn_close)
        vbox.addLayout(footer)

    def _build_validation_tab(self) -> QWidget:
        page = QWidget()
        vbox = QVBoxLayout(page)
        vbox.setContentsMargins(8, 8, 8, 8)
        vbox.setSpacing(8)

        lbl_col = QLabel("PHYSICAL COLLISION-RISK WARNINGS (MANUAL VERIFICATION REQUIRED)", page)
        lbl_col.setObjectName("SectionHeader")
        vbox.addWidget(lbl_col)

        list_col = QListWidget(page)
        list_col.setMaximumHeight(105)
        for cw in self.report.collision_risk_warnings:
            list_col.addItem(f"⚠ {cw}")
        vbox.addWidget(list_col)

        lbl_iss = QLabel("VALIDATION ISSUES (EXACT COORDINATES & RESPONSIBLE COMMANDS)", page)
        lbl_iss.setObjectName("SectionHeader")
        vbox.addWidget(lbl_iss)

        table = QTableWidget(len(self.report.issues), 5, page)
        table.setHorizontalHeaderLabels(["Severity", "Code / Title", "Line", "Coordinates (X, Y, Z)", "Command & Details"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        for row, iss in enumerate(self.report.issues):
            sev_item = QTableWidgetItem(iss.severity.value.upper())
            if iss.severity == ValidationSeverity.CRITICAL:
                sev_item.setForeground(QColor("#EF4444"))
            elif iss.severity == ValidationSeverity.WARNING:
                sev_item.setForeground(QColor("#F59E0B"))
            else:
                sev_item.setForeground(QColor("#22C55E"))

            title_item = QTableWidgetItem(f"{iss.code}: {iss.title}")
            line_item = QTableWidgetItem(str(iss.line_number or "-"))
            coord_str = (
                f"({iss.coordinates[0]:.2f}, {iss.coordinates[1]:.2f}, {iss.coordinates[2]:.2f}) mm"
                if iss.coordinates
                else "-"
            )
            coord_item = QTableWidgetItem(coord_str)
            detail_str = f"{iss.command} — {iss.message}" if iss.command else iss.message
            detail_item = QTableWidgetItem(detail_str)

            table.setItem(row, 0, sev_item)
            table.setItem(row, 1, title_item)
            table.setItem(row, 2, line_item)
            table.setItem(row, 3, coord_item)
            table.setItem(row, 4, detail_item)

        vbox.addWidget(table, 1)
        return page

    def _build_gcode_tab(self) -> QWidget:
        page = QWidget()
        vbox = QVBoxLayout(page)
        vbox.setContentsMargins(8, 8, 8, 8)

        editor = QPlainTextEdit(page)
        editor.setReadOnly(True)
        editor.setStyleSheet('font-family: "Cascadia Mono", "Consolas", monospace; font-size: 11px;')

        numbered_lines = [
            f"{idx:5d} | {line}"
            for idx, line in enumerate(self.gcode_text.splitlines(), start=1)
        ]
        editor.setPlainText("\n".join(numbered_lines))
        vbox.addWidget(editor, 1)
        return page
