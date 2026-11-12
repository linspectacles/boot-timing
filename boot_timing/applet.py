#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# LinSpectacles - Linux Inspection Suite
# Copyright (C) 2026 brunonlinespace
# GPL-3.0-or-later

APPLET_ID = 'linspectacles-boot-timing'
APPLET_NAME = 'Boot Timing'
APPLET_VERSION = '0.0.10'
APPLET_AUTHOR = "brunonlinespace"
APPLET_EDITOR = "brunonlinespace"
APPLET_PUBLISHER = "brunonlinespace"
APPLET_ORGANIZATION_ID = "linspectacles"
APPLET_ORGANIZATION_URL = "https://github.com/linspectacles/"
APPLET_REPOSITORY = "https://github.com/linspectacles/boot-timing"

import os
import re
import shutil
import subprocess
import threading
from pathlib import Path
from PyQt6.QtCore import QObject, QSettings, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QKeySequence, QPixmap, QShortcut, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QDialog, QDialogButtonBox, QComboBox, QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QTabWidget, QTextEdit, QVBoxLayout, QWidget)
from ._support import (NumericTableWidgetItem, ColumnVisibilityController, MetadataHighlighter, apply_metadata_font, metadata_font_qss, export_records_dialog)


class _UnitDetailsBridge(QObject):
    """Thread-safe delivery of deferred selected-unit timing results."""

    ready = pyqtSignal(int, str, object, str)


BOOT_TIMING_SOURCES_TEXT = (
    "Boot timing summary\n"
    "  systemd-analyze --no-pager time\n\n"
    "Measured boot units, durations and unit-type categories\n"
    "  systemd-analyze --no-pager blame\n"
    "  Category is derived mechanically from each reported unit name suffix (for example .service or .mount).\n\n"
    "Critical chain\n"
    "  systemd-analyze --no-pager critical-chain\n"
    "  systemd-analyze --no-pager critical-chain <selected-unit>\n"
    "  The global critical chain is shown in Overall Timing; the selected-unit chain is acquired only when Unit Critical Path is requested.\n\n"
    "Boot milestone and selected-unit timing properties\n"
    "  systemctl show <target-or-unit> --no-pager --property=<timing-properties>\n"
    "  Monotonic timestamps shown by Overall Timing and Metadata Details are reported directly from systemd microsecond values.\n\n"
    "Boot log supporting view\n"
    "  /var/log/boot.log\n"
    "  Read directly when permitted; if the file exists but is not readable, the Boot Log tab can request privileged read access for this exact file only.\n\n"
    "Command environment\n"
    "  SYSTEMD_COLORS=0\n"
    "  SYSTEMD_PAGER=cat\n\n"
    "Boot Timing is read-only. It does not start, stop, enable, disable, restart, "
    "or otherwise change systemd units or boot configuration."
)




def _apply_details_font(owner, widget):
    font = getattr(owner, "_metadata_font", None)
    if font is not None:
        widget.setFont(font)
        widget.document().setDefaultFont(font)
        widget.setCurrentFont(font)


def _timing_details_canvas(owner):
    """Systemd-Unit-Details-style metadata canvas for Boot Timing."""
    widget = QTextEdit()
    widget.setReadOnly(True)
    widget.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
    _apply_details_font(owner, widget)
    font = getattr(owner, "_metadata_font", None)
    font_rule = metadata_font_qss(font) if font is not None else ""
    widget.setStyleSheet(
        "QTextEdit { "
        f"{font_rule} "
        "background-color: #151719; color: #dcdcdc; "
        "border: 1px solid #333333; "
        "}"
    )
    return widget


def _timing_detail_formats():
    key_format = QTextCharFormat()
    key_format.setForeground(QColor("#9cdcfe"))
    key_format.setFontWeight(600)
    value_format = QTextCharFormat()
    value_format.setForeground(QColor("#dcdcdc"))
    return key_format, value_format


def _timing_append_heading(widget, heading):
    key_format, value_format = _timing_detail_formats()
    cursor = widget.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    if cursor.position() > 0:
        cursor.insertText("\n", value_format)
    cursor.insertText(str(heading) + "\n", key_format)
    widget.setTextCursor(cursor)


def _timing_append_property(widget, key, value):
    key_format, value_format = _timing_detail_formats()
    cursor = widget.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    cursor.insertText(f"{key}: ", key_format)
    text = str(value) if str(value or "") else "Not reported"
    cursor.insertText(text + "\n", value_format)
    widget.setTextCursor(cursor)


def _timing_scroll_top(widget):
    cursor = widget.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.Start)
    widget.setTextCursor(cursor)
    widget.verticalScrollBar().setValue(0)


class BootTimingDetailsDialog(QDialog):
    """Boot-wide overall timing view using the Systemd Unit Details dialog pattern."""

    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.setWindowTitle("Overall Timing — Boot Timing")
        self.resize(980, 720)

        root = QVBoxLayout(self)
        note = QLabel(
            "Boot-wide timing information reported by systemd. Measured unit durations may overlap; "
            "a long duration does not by itself mean that a unit delayed boot. Unit-specific timing "
            "metadata remains in the main Metadata Details pane; Unit Critical Path is requested separately."
        )
        note.setWordWrap(True)
        root.addWidget(note)

        tabs = QTabWidget()
        root.addWidget(tabs, 1)

        critical_page = QWidget()
        critical_layout = QVBoxLayout(critical_page)
        critical_canvas = _timing_details_canvas(owner)
        owner._populate_global_critical_chain_canvas(critical_canvas)
        critical_layout.addWidget(critical_canvas, 1)
        tabs.addTab(critical_page, "Critical Chain")

        phases_page = QWidget()
        phases_layout = QVBoxLayout(phases_page)
        phases_canvas = _timing_details_canvas(owner)
        owner._populate_boot_phases_canvas(phases_canvas)
        phases_layout.addWidget(phases_canvas, 1)
        tabs.addTab(phases_page, "Boot Phases")

        milestones_page = QWidget()
        milestones_layout = QVBoxLayout(milestones_page)
        milestones_canvas = _timing_details_canvas(owner)
        owner._populate_milestones_canvas(milestones_canvas)
        milestones_layout.addWidget(milestones_canvas, 1)
        tabs.addTab(milestones_page, "Milestones")

        boot_log_page = QWidget()
        boot_log_layout = QVBoxLayout(boot_log_page)
        self.boot_log_canvas = _timing_details_canvas(owner)
        boot_log_layout.addWidget(self.boot_log_canvas, 1)

        self.boot_log_privileged_btn = QPushButton("Privileged Access...")
        self.boot_log_privileged_btn.clicked.connect(self._read_boot_log_privileged)
        self.boot_log_privileged_btn.setVisible(False)
        boot_log_layout.addWidget(self.boot_log_privileged_btn, alignment=Qt.AlignmentFlag.AlignRight)

        tabs.addTab(boot_log_page, "Boot Log")
        self._read_boot_log_ordinary()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)


    def _show_boot_log(self, access, text, status=None):
        self.boot_log_canvas.clear()
        _timing_append_heading(self.boot_log_canvas, "Boot Log")
        _timing_append_property(self.boot_log_canvas, "Source", "/var/log/boot.log")
        _timing_append_property(self.boot_log_canvas, "Access", access)
        if status:
            _timing_append_property(self.boot_log_canvas, "Status", status)
        if text:
            cursor = self.boot_log_canvas.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.insertText("\n" + text.rstrip() + "\n")
            self.boot_log_canvas.setTextCursor(cursor)
        _timing_scroll_top(self.boot_log_canvas)

    def _read_boot_log_ordinary(self):
        path = Path("/var/log/boot.log")
        self.boot_log_privileged_btn.setVisible(False)
        if not path.exists():
            self._show_boot_log("Ordinary", "", "Boot log is not available on this system.")
            return
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except PermissionError:
            self._show_boot_log("Restricted", "", "Boot log is available but requires privileged access.")
            self.boot_log_privileged_btn.setVisible(shutil.which("pkexec") is not None and shutil.which("cat") is not None)
            return
        except OSError as exc:
            self._show_boot_log("Ordinary", "", f"Unable to read boot log: {exc}")
            return
        display_text = text.replace("\x00", "")
        if not display_text.strip():
            try:
                size = path.stat().st_size
            except OSError:
                size = 0
            status = "Boot log is empty." if size == 0 else "Boot log contains no displayable text."
            self._show_boot_log("Ordinary", "", status)
            return
        self._show_boot_log("Ordinary", display_text, "Read successfully.")

    def _read_boot_log_privileged(self):
        pkexec = shutil.which("pkexec")
        cat = shutil.which("cat")
        if pkexec is None or cat is None:
            self._show_boot_log("Restricted", "", "Privileged boot-log reading is unavailable because pkexec or cat was not found.")
            self.boot_log_privileged_btn.setVisible(False)
            return
        try:
            result = subprocess.run(
                [pkexec, cat, "/var/log/boot.log"],
                capture_output=True,
                text=True,
                check=False,
                timeout=60,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            self._show_boot_log("Privileged", "", f"Unable to read boot log with privileged access: {exc}")
            return
        if result.returncode != 0:
            detail = (result.stderr or "Privileged boot-log read was cancelled or failed.").strip()
            self._show_boot_log("Privileged", "", detail)
            return
        self.boot_log_privileged_btn.setVisible(False)
        display_text = (result.stdout or "").replace("\x00", "")
        if not display_text.strip():
            self._show_boot_log("Privileged", "", "Privileged read completed, but the boot log is empty.")
            return
        self._show_boot_log("Privileged", display_text, "Read successfully.")


class UnitCriticalPathDialog(QDialog):
    """Explicit selected-unit critical-path inspection."""

    chain_ready = pyqtSignal(str)

    def __init__(self, owner, unit_name):
        super().__init__(owner)
        self.owner = owner
        self.unit_name = str(unit_name or "")
        self.setWindowTitle(f"Unit Critical Path — {self.unit_name}")
        self.resize(900, 620)

        root = QVBoxLayout(self)
        self.canvas = _timing_details_canvas(owner)
        root.addWidget(self.canvas, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.chain_ready.connect(self._show_chain)
        cached = owner._unit_chain_cache.get(self.unit_name)
        if cached is not None:
            self._show_chain(cached)
        else:
            self.canvas.setPlainText("Inspecting selected unit critical path...")
            _apply_details_font(owner, self.canvas)
            QTimer.singleShot(0, self._start_inspection)

    def _start_inspection(self):
        worker = threading.Thread(
            target=self._collect_chain,
            name=f"boot-timing-unit-critical-path:{self.unit_name}",
            daemon=True,
        )
        worker.start()

    def _collect_chain(self):
        text = self.owner._selected_unit_chain(self.unit_name)
        try:
            self.chain_ready.emit(text)
        except RuntimeError:
            pass

    def _show_chain(self, text):
        self.canvas.clear()
        key_format, value_format = _timing_detail_formats()
        cursor = self.canvas.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        # Plain-text specialist dialogs follow the same visual convention as
        # the canonical Sources canvas: blue heading/key text and neutral
        # light body text on the shared dark metadata surface.
        cursor.insertText("Unit Critical Path\n\n", key_format)
        cursor.insertText((str(text or "No critical-chain data was returned.")).rstrip() + "\n", value_format)
        self.canvas.setTextCursor(cursor)
        _timing_scroll_top(self.canvas)


class BootTimingOptionsDialog(QDialog):
    """Tabbed Boot Timing options using established LinSpectacles dialog patterns."""

    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.setWindowTitle("Options — Boot Timing")
        self.resize(980, 720)

        root = QVBoxLayout(self)
        tabs = QTabWidget()
        root.addWidget(tabs, 1)

        # Configuration — existing display settings and global-path filter.
        appearance_page = QWidget()
        appearance_layout = QVBoxLayout(appearance_page)
        appearance_layout.setContentsMargins(12, 12, 12, 12)
        appearance_layout.setSpacing(10)

        appearance_heading = QLabel("Metadata display")
        appearance_heading_font = appearance_heading.font()
        appearance_heading_font.setBold(True)
        appearance_heading.setFont(appearance_heading_font)
        appearance_layout.addWidget(appearance_heading)

        appearance_note = QLabel(
            "Choose which measured boot units are displayed and how the Measured Boot Units and Metadata Details panes are arranged. "
            "Shortcuts: Shift+F5 runs Scan/Scan Again, F4 opens Unit Critical Path for the selected unit, "
            "Ctrl+L toggles Horizontal/Vertical, F3 shows or hides Metadata Details, "
            "Ctrl+G toggles Global Path Only, and Ctrl+/ opens Options. "
            "Overall Timing has no assigned shortcut. These Boot Timing settings are remembered."
        )
        appearance_note.setWordWrap(True)
        appearance_layout.addWidget(appearance_note)

        layout_row = QHBoxLayout()
        layout_row.addWidget(QLabel("View layout:"))
        self.layout_combo = QComboBox()
        self.layout_combo.addItems(["Horizontal", "Vertical"])
        self.layout_combo.setCurrentText(
            "Vertical" if owner.details_orientation == "vertical" else "Horizontal"
        )
        self.layout_combo.currentTextChanged.connect(self._layout_changed)
        layout_row.addWidget(self.layout_combo)
        layout_row.addStretch(1)
        appearance_layout.addLayout(layout_row)

        self.metadata_checkbox = QCheckBox("Show Metadata Details")
        self.metadata_checkbox.setChecked(owner.details_visible)
        self.metadata_checkbox.toggled.connect(self._metadata_visibility_changed)
        appearance_layout.addWidget(self.metadata_checkbox)

        global_path_heading = QLabel("Measured Boot Units")
        global_path_heading_font = global_path_heading.font()
        global_path_heading_font.setBold(True)
        global_path_heading.setFont(global_path_heading_font)
        appearance_layout.addWidget(global_path_heading)

        self.global_path_checkbox = QCheckBox("Global Path Only (Ctrl+G)")
        self.global_path_checkbox.setChecked(owner.global_path_only)
        self.global_path_checkbox.toggled.connect(self._global_path_only_changed)
        appearance_layout.addWidget(self.global_path_checkbox)

        global_path_note = QLabel(
            "Show only measured boot units on the reported global critical path. "
            "When unchecked, all measured boot units are shown (subject to Search and Category filters)."
        )
        global_path_note.setWordWrap(True)
        appearance_layout.addWidget(global_path_note)

        appearance_layout.addStretch(1)
        tabs.addTab(appearance_page, "Configuration")

        # Sources — former top-level Sources dialog content.
        sources_page = QWidget()
        sources_layout = QVBoxLayout(sources_page)
        sources_layout.setContentsMargins(12, 12, 12, 12)
        sources_layout.setSpacing(10)

        sources_heading = QLabel("Data Sources")
        sources_heading_font = sources_heading.font()
        sources_heading_font.setBold(True)
        sources_heading_font.setPointSize(max(sources_heading_font.pointSize(), 11))
        sources_heading.setFont(sources_heading_font)
        sources_layout.addWidget(sources_heading)

        sources_note = QLabel(
            "Commands and system interfaces used by the read-only Boot Timing applet."
        )
        sources_note.setWordWrap(True)
        sources_layout.addWidget(sources_note)

        sources_canvas = _timing_details_canvas(owner)
        key_format, value_format = _timing_detail_formats()
        cursor = sources_canvas.textCursor()
        for line in BOOT_TIMING_SOURCES_TEXT.splitlines():
            if line and not line.startswith(" ") and not line.startswith("Boot Timing is read-only"):
                cursor.insertText(line + "\n", key_format)
            else:
                cursor.insertText(line + "\n", value_format)
        sources_canvas.setTextCursor(cursor)
        _timing_scroll_top(sources_canvas)
        sources_layout.addWidget(sources_canvas, 1)
        tabs.addTab(sources_page, "Sources")

        # Export — report components, deliberately not inventory-row dependent.
        export_page = QWidget()
        export_layout = QVBoxLayout(export_page)
        export_layout.setContentsMargins(12, 12, 12, 12)
        export_layout.setSpacing(10)

        export_heading = QLabel("Export details")
        export_heading_font = export_heading.font()
        export_heading_font.setBold(True)
        export_heading.setFont(export_heading_font)
        export_layout.addWidget(export_heading)

        export_note = QLabel(
            "Select the Boot Timing report components to include in the export."
        )
        export_note.setWordWrap(True)
        export_layout.addWidget(export_note)

        self.export_summary = QCheckBox("Boot Summary")
        self.export_phases = QCheckBox("Boot Phase Breakdown")
        self.export_milestones = QCheckBox("Target Milestones")
        self.export_units = QCheckBox("Measured Boot Units")
        self.export_chain = QCheckBox("Critical Chain")
        self.export_status = QCheckBox("Status Bar Summary")
        for checkbox in (
            self.export_summary,
            self.export_phases,
            self.export_milestones,
            self.export_units,
            self.export_chain,
            self.export_status,
        ):
            checkbox.setChecked(True)
            export_layout.addWidget(checkbox)

        export_layout.addStretch(1)
        export_row = QHBoxLayout()
        export_row.addStretch(1)
        export_button = QPushButton("Export...")
        export_button.clicked.connect(self._export_selected)
        export_row.addWidget(export_button)
        export_layout.addLayout(export_row)
        tabs.addTab(export_page, "Export")

        # About — established LinSpectacles applet About composition.
        about_page = QWidget()
        about_layout = QVBoxLayout(about_page)
        about_layout.setContentsMargins(24, 20, 24, 18)
        about_layout.setSpacing(8)

        icon_label = QLabel()
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setFixedSize(112, 112)
        icon_path = Path(__file__).resolve().parent / "icon.png"
        if icon_path.is_file():
            pixmap = QPixmap(str(icon_path))
            if not pixmap.isNull():
                icon_label.setPixmap(
                    pixmap.scaled(
                        112,
                        112,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
        about_layout.addWidget(icon_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        name = QLabel("<h2 style='margin:0'>Boot Timing</h2>")
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_layout.addWidget(name)

        version = QLabel(f"Version {APPLET_VERSION}")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_layout.addWidget(version)

        slogan = QLabel("<b>Expose. Explore. Explain.</b>")
        slogan.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_layout.addWidget(slogan)

        description = QLabel(
            "A read-only LinSpectacles applet for inspecting systemd boot timing, "
            "measured unit startup durations, boot phases, target milestones and critical paths."
        )
        description.setWordWrap(True)
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_layout.addWidget(description)

        details = QLabel(
            "<b>Build:</b> Standalone LinSpectacles applet<br>"
            "<b>Organisation ID:</b> "
            f"<a href='{APPLET_ORGANIZATION_URL}'>{APPLET_ORGANIZATION_ID}</a><br>"
            f"<b>Applet ID:</b> {APPLET_ID}"
        )
        details.setWordWrap(True)
        details.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction
            | Qt.TextInteractionFlag.TextSelectableByMouse
        )
        details.setOpenExternalLinks(True)
        details.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_layout.addWidget(details)

        copyright_label = QLabel(
            "Copyright © 2026 "
            "<a href='https://github.com/brunonlinespace'>brunonlinespace</a>"
        )
        copyright_label.setOpenExternalLinks(True)
        copyright_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_layout.addWidget(copyright_label)

        license_label = QLabel("Licensed under GNU GPLv3 or later.")
        license_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_layout.addWidget(license_label)

        readme_url = QUrl.fromLocalFile(
            str(Path(__file__).resolve().parent.parent / "README.md")
        ).toString()
        license_url = QUrl.fromLocalFile(
            str(Path(__file__).resolve().parent.parent / "LICENSE")
        ).toString()
        links = QLabel(
            f"<a href='{readme_url}'>README</a> &nbsp;·&nbsp; "
            f"<a href='{license_url}'>License</a> &nbsp;·&nbsp; "
            f"<a href='{APPLET_REPOSITORY}'>Repository</a>"
        )
        links.setOpenExternalLinks(True)
        links.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_layout.addWidget(links)
        about_layout.addStretch(1)
        tabs.addTab(about_page, "About")

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _layout_changed(self, text):
        self.owner.set_details_orientation(str(text).strip().lower(), persist=True)

    def _metadata_visibility_changed(self, checked):
        self.owner.set_details_visible(bool(checked), persist=True)

    def _global_path_only_changed(self, checked):
        self.owner.set_global_path_only(bool(checked), persist=True)

    def _export_selected(self):
        if not self.owner.has_scanned:
            QMessageBox.information(self, "Export", "Boot data has not been scanned yet.")
            return

        record = {}
        columns = []
        if self.export_summary.isChecked():
            record["boot_summary"] = self.owner.summary_text
            columns.append(("boot_summary", "Boot Summary", 520, "left"))
        if self.export_phases.isChecked():
            record["boot_phase_breakdown"] = self.owner._phase_breakdown_export_text()
            columns.append(("boot_phase_breakdown", "Boot Phase Breakdown", 520, "left"))
        if self.export_milestones.isChecked():
            record["target_milestones"] = self.owner._milestones_export_text()
            columns.append(("target_milestones", "Target Milestones", 520, "left"))
        if self.export_units.isChecked():
            record["measured_boot_units"] = self.owner._measured_units_export_text()
            columns.append(("measured_boot_units", "Measured Boot Units", 520, "left"))
        if self.export_chain.isChecked():
            record["critical_chain"] = self.owner.global_chain_text
            columns.append(("critical_chain", "Critical Chain", 520, "left"))
        if self.export_status.isChecked():
            record["status_bar_summary"] = self.owner.status_summary_text
            columns.append(("status_bar_summary", "Status Bar Summary", 520, "left"))

        if not columns:
            QMessageBox.information(
                self, "Export", "Select at least one report component to export."
            )
            return

        path = export_records_dialog(
            self, APPLET_NAME, [record], columns=columns
        )
        if path is not None:
            self.owner.status_lbl.setText(f"Exported boot data to {path}")


class BootTimingWidget(QWidget):
    """Read-only systemd boot timing inspector."""

    ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
    DURATION_PART_RE = re.compile(r"(\d+(?:\.\d+)?)(h|min|ms|us|µs|s)")
    BLAME_LINE_RE = re.compile(
        r"^\s*((?:(?:\d+(?:\.\d+)?)(?:h|min|ms|us|µs|s)\s*)+)\s+(.+?)\s*$"
    )

    def __init__(self, parent=None, autoload=False):
        super().__init__(parent)
        self.records = []
        self.has_scanned = False
        self.phase_data = {}
        self._milestone_cache = None
        self._unit_timing_cache = {}
        self._unit_chain_cache = {}
        self._details_generation = 0
        self._detail_inflight = {}
        self._pending_detail_unit = None
        self._detail_bridge = _UnitDetailsBridge(self)
        self._detail_bridge.ready.connect(self._apply_unit_details_result)
        self._detail_debounce_timer = QTimer(self)
        self._detail_debounce_timer.setSingleShot(True)
        self._detail_debounce_timer.setInterval(160)
        self._detail_debounce_timer.timeout.connect(self._launch_pending_unit_details)
        self.global_chain_text = "Boot critical-chain data has not been scanned yet."
        self._global_path_units = set()
        self._global_path_available = None
        self.global_path_only = False
        self.setup_ui()
        if autoload:
            self.load_boot_data()

    def setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        top = QHBoxLayout()
        self.stats_label = QLabel("Measured Boot Units: Not scanned")
        stats_font = self.stats_label.font()
        stats_font.setBold(True)
        stats_font.setPointSize(max(stats_font.pointSize(), 11))
        self.stats_label.setFont(stats_font)
        top.addWidget(self.stats_label)
        top.addStretch(1)

        self.refresh_btn = QPushButton("Scan")
        self.refresh_btn.clicked.connect(self.load_boot_data)
        top.addWidget(self.refresh_btn)

        self.unit_chain_btn = QPushButton("Unit Critical Path...")
        self.unit_chain_btn.setEnabled(False)
        self.unit_chain_btn.clicked.connect(self.show_unit_critical_path)
        top.addWidget(self.unit_chain_btn)

        self.overall_timing_btn = QPushButton("Overall Timing...")
        self.overall_timing_btn.setEnabled(False)
        self.overall_timing_btn.clicked.connect(self.show_overall_timing)
        top.addWidget(self.overall_timing_btn)

        self.options_btn = QPushButton("Options...")
        self.options_btn.clicked.connect(self.show_options)
        top.addWidget(self.options_btn)
        root.addLayout(top)

        self.summary_text = "Boot data has not been scanned yet."

        filter_layout = QHBoxLayout()
        search_label = QLabel("Search:")
        search_label.setStyleSheet("font-weight: 600;")
        filter_layout.addWidget(search_label)

        self.search_entry = QLineEdit()
        self.search_entry.setPlaceholderText("Search boot units...")
        self.search_entry.setMaximumWidth(280)
        self.search_entry.textChanged.connect(self.filter_units)
        filter_layout.addWidget(self.search_entry)

        category_label = QLabel("Category:")
        category_label.setStyleSheet("font-weight: 600;")
        filter_layout.addWidget(category_label)

        self.category_dropdown = QComboBox()
        self.category_dropdown.addItems([
            "All Categories",
            "Service",
            "Mount",
            "Device",
            "Socket",
            "Target",
            "Timer",
            "Swap",
            "Path",
            "Automount",
            "Slice",
            "Scope",
            "Other",
        ])
        self.category_dropdown.setMinimumWidth(190)
        self.category_dropdown.currentTextChanged.connect(self.filter_units)
        filter_layout.addWidget(self.category_dropdown)

        self.filter_status_lbl = QLabel("")
        filter_font = self.filter_status_lbl.font()
        filter_font.setItalic(True)
        self.filter_status_lbl.setFont(filter_font)
        filter_layout.addWidget(self.filter_status_lbl)
        filter_layout.addStretch(1)
        root.addLayout(filter_layout)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(self.splitter, 1)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Duration", "Unit", "Category"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setSortingEnabled(True)
        self.table.setColumnWidth(0, 110)
        self.table.setColumnWidth(1, 360)
        self.table.setColumnWidth(2, 135)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.column_visibility = ColumnVisibilityController(
            self.table,
            [("duration", "Duration", 110, "right"), ("unit", "Unit", 360, "left"), ("category", "Category", 135, "left")],
            lambda text: self.status_lbl.setText(text) if hasattr(self, "status_lbl") else None,
        )
        self.splitter.addWidget(self.table)

        self.details_panel = QWidget()
        self.details_layout = QVBoxLayout(self.details_panel)
        self.details_layout.setContentsMargins(8, 0, 0, 0)

        details_label = QLabel("Metadata Details")
        details_font = details_label.font()
        details_font.setBold(True)
        details_font.setPointSize(max(details_font.pointSize(), 11))
        details_label.setFont(details_font)
        self.details_layout.addWidget(details_label)

        self.details_text = QTextEdit()
        self.details_text.setReadOnly(True)
        self._metadata_font = apply_metadata_font(self.details_text)
        self.details_text.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        # Main Metadata Details follows the authoritative Kernel Modules convention.
        self._details_text_bg = "#1e1e1e"
        self._details_text_fg = "#dcdcdc"
        self._details_key_fg = "#4ec9b0"
        self._details_value_fg = "#ce9178"
        self.metadata_highlighter = MetadataHighlighter(self.details_text.document())
        self.metadata_highlighter.set_colors(
            self._details_key_fg, self._details_value_fg, self._details_text_fg
        )
        self._update_details_style()
        self.details_text.setPlainText("Select a measured boot unit to inspect its timing metadata.")
        self.details_layout.addWidget(self.details_text, 1)
        self.splitter.addWidget(self.details_panel)
        self.splitter.setSizes([520, 660])
        self.table.itemSelectionChanged.connect(self._on_unit_selection_changed)

        self.details_orientation = "horizontal"
        self.details_visible = True
        self._load_details_orientation()
        self._load_details_visibility()
        self._install_shortcuts()

        self.status_summary_text = "Not scanned - Select Scan to inspect the current boot."
        self.status_lbl = QLabel(self.status_summary_text)
        status_font = self.status_lbl.font()
        status_font.setItalic(True)
        self.status_lbl.setFont(status_font)
        self.status_lbl.setFrameShape(QFrame.Shape.NoFrame)
        self.status_lbl.setWordWrap(False)
        self.status_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.status_lbl.setContentsMargins(4, 4, 4, 4)
        root.addWidget(self.status_lbl)
        self._load_global_path_only()

    def _update_details_style(self):
        # Exact main-pane styling convention from Kernel Modules BaseInspectorTab.
        self.details_text.setStyleSheet(
            "QTextEdit { "
            f"background: {self._details_text_bg}; color: {self._details_text_fg}; "
            "border: 1px solid #666; "
            f"{metadata_font_qss(self._metadata_font)} "
            "}"
        )

    def apply_host_settings(self, settings=None, column_visibility_callback=None):
        settings = settings or {}
        self._metadata_font = apply_metadata_font(
            self.details_text, settings.get("metadata_font", "")
        )
        self._update_details_style()
        self.column_visibility.set_changed_callback(column_visibility_callback)
        self.column_visibility.apply_hidden(settings.get("hidden_columns", []))

    def show_options(self):
        dialog = BootTimingOptionsDialog(self)
        dialog.exec()

    def _trigger_scan_shortcut(self):
        if self.refresh_btn.isEnabled():
            self.load_boot_data()

    def _install_shortcuts(self):
        self._shortcuts = []
        for sequence, callback in (
            ("Shift+F5", self._trigger_scan_shortcut),
            ("F4", self.show_unit_critical_path),
            ("Ctrl+/", self.show_options),
            ("Ctrl+L", self.toggle_details_orientation),
            ("F3", self.toggle_details_visibility),
            ("Ctrl+G", self.toggle_global_path_only),
        ):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(callback)
            self._shortcuts.append(shortcut)

    def _load_global_path_only(self):
        settings = QSettings("brunonlinespace", "Boot Timing")
        value = settings.value("global_path_only", False)
        if isinstance(value, str):
            self.global_path_only = value.strip().lower() not in {"0", "false", "no", "off"}
        else:
            self.global_path_only = bool(value)

    def set_global_path_only(self, enabled, *, persist=True):
        self.global_path_only = bool(enabled)
        if persist:
            settings = QSettings("brunonlinespace", "Boot Timing")
            settings.setValue("global_path_only", self.global_path_only)
            settings.sync()
        self.filter_units()

    def toggle_global_path_only(self):
        self.set_global_path_only(not self.global_path_only)

    def _load_details_visibility(self):
        settings = QSettings("brunonlinespace", "Boot Timing")
        value = settings.value("details_visible", True)
        if isinstance(value, str):
            visible = value.strip().lower() not in {"0", "false", "no", "off"}
        else:
            visible = bool(value)
        self.set_details_visible(visible, persist=False)

    def set_details_visible(self, visible, *, persist=True):
        self.details_visible = bool(visible)
        self.details_panel.setVisible(self.details_visible)
        if self.details_visible:
            self.set_details_orientation(self.details_orientation, persist=False)
        if persist:
            settings = QSettings("brunonlinespace", "Boot Timing")
            settings.setValue("details_visible", self.details_visible)
            settings.sync()

    def toggle_details_visibility(self):
        self.set_details_visible(not self.details_visible, persist=True)

    def toggle_details_orientation(self):
        orientation = "vertical" if self.details_orientation == "horizontal" else "horizontal"
        self.set_details_orientation(orientation, persist=True)

    def _load_details_orientation(self):
        settings = QSettings("brunonlinespace", "Boot Timing")
        orientation = str(
            settings.value("details_orientation", "horizontal") or "horizontal"
        ).lower()
        if orientation not in {"horizontal", "vertical"}:
            orientation = "horizontal"
        self.set_details_orientation(orientation, persist=False)

    def set_details_orientation(self, orientation, *, persist=True):
        orientation = str(orientation or "horizontal").lower()
        if orientation not in {"horizontal", "vertical"}:
            orientation = "horizontal"
        self.details_orientation = orientation

        if orientation == "vertical":
            self.splitter.setOrientation(Qt.Orientation.Vertical)
            self.details_layout.setContentsMargins(0, 8, 0, 0)
            self.splitter.setSizes([430, 330])
        else:
            self.splitter.setOrientation(Qt.Orientation.Horizontal)
            self.details_layout.setContentsMargins(8, 0, 0, 0)
            self.splitter.setSizes([520, 660])

        if persist:
            settings = QSettings("brunonlinespace", "Boot Timing")
            settings.setValue("details_orientation", orientation)
            settings.sync()

    def _measured_units_export_text(self):
        if not self.records:
            return "No measured boot units were returned."
        lines = []
        for record in self.records:
            lines.append(
                f"{record.get('duration', '')}  {record.get('unit', '')}  [{record.get('category', '')}]"
            )
        return "\n".join(lines)

    @staticmethod
    def _systemd_environment():
        env = os.environ.copy()
        env["SYSTEMD_COLORS"] = "0"
        env["SYSTEMD_PAGER"] = "cat"
        return env

    def _run_systemd_analyze(self, *arguments, timeout=10):
        return subprocess.run(
            ["systemd-analyze", "--no-pager", *arguments],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
            env=self._systemd_environment(),
        )

    @classmethod
    def _duration_seconds(cls, text):
        total = 0.0
        multipliers = {
            "h": 3600.0,
            "min": 60.0,
            "s": 1.0,
            "ms": 0.001,
            "us": 0.000001,
            "µs": 0.000001,
        }
        for value, unit in cls.DURATION_PART_RE.findall(text):
            total += float(value) * multipliers[unit]
        return total

    @classmethod
    def _plain_critical_chain(cls, text):
        text = cls.ANSI_ESCAPE_RE.sub("", text or "")
        replacements = {
            "●": "",
            "└─": "  ",
            "├─": "  ",
            "│": " ",
            "└": " ",
            "├": " ",
            "─": "-",
        }
        for source, target in replacements.items():
            text = text.replace(source, target)
        return "\n".join(line.rstrip() for line in text.splitlines()).strip()

    @classmethod
    def _global_path_unit_names(cls, text):
        """Return the systemd unit names explicitly reported by one global critical-chain."""
        plain = cls._plain_critical_chain(text)
        units = set()
        for line in plain.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            candidate = stripped.split(None, 1)[0]
            if cls._unit_category(candidate) != "Other":
                units.add(candidate)
        return units

    @staticmethod
    def _unit_category(unit_name):
        suffix_map = (
            (".service", "Service"),
            (".mount", "Mount"),
            (".device", "Device"),
            (".socket", "Socket"),
            (".target", "Target"),
            (".timer", "Timer"),
            (".swap", "Swap"),
            (".path", "Path"),
            (".automount", "Automount"),
            (".slice", "Slice"),
            (".scope", "Scope"),
        )
        name = str(unit_name or "").lower()
        for suffix, category in suffix_map:
            if name.endswith(suffix):
                return category
        return "Other"

    @staticmethod
    def _category_color(category):
        # Reuse the restrained category palette established by Kernel Modules.
        color_map = {
            "Service": "#ce9178",
            "Mount": "#c586c0",
            "Device": "#9cdcfe",
            "Socket": "#4ec9b0",
            "Target": "#dcdcaa",
            "Timer": "#b5cea8",
            "Swap": "#c586c0",
            "Path": "#9cdcfe",
            "Automount": "#c586c0",
            "Slice": "#dcdcaa",
            "Scope": "#4ec9b0",
            "Other": "#9a9a9a",
        }
        return color_map.get(category, "#9a9a9a")

    def _parse_blame(self, text):
        records = []
        for line in (text or "").splitlines():
            match = self.BLAME_LINE_RE.match(line)
            if not match:
                continue
            duration_text = " ".join(match.group(1).split())
            unit_name = match.group(2).strip()
            records.append(
                {
                    "duration": duration_text,
                    "seconds": self._duration_seconds(duration_text),
                    "unit": unit_name,
                    "category": self._unit_category(unit_name),
                }
            )
        return records

    def filter_units(self, *_):
        query = self.search_entry.text().strip().lower()
        selected_category = self.category_dropdown.currentText()

        def matches_view(record):
            on_global_path = record.get("unit", "") in self._global_path_units
            if self.global_path_only:
                return self._global_path_available is True and on_global_path
            return True

        matches = [
            record for record in self.records
            if (
                not query
                or query in record["unit"].lower()
                or query in record["duration"].lower()
                or query in record["category"].lower()
            )
            and (selected_category == "All Categories" or record["category"] == selected_category)
            and matches_view(record)
        ]

        was_sorting = self.table.isSortingEnabled()
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(matches))
        for row, record in enumerate(matches):
            duration_item = NumericTableWidgetItem(
                record["duration"], record["seconds"]
            )
            duration_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self.table.setItem(row, 0, duration_item)
            unit_item = QTableWidgetItem(record["unit"])
            unit_item.setData(Qt.ItemDataRole.UserRole, dict(record))
            self.table.setItem(row, 1, unit_item)
            category_item = QTableWidgetItem(record["category"])
            category_item.setForeground(QBrush(QColor(self._category_color(record["category"]))))
            self.table.setItem(row, 2, category_item)
        self.table.setSortingEnabled(was_sorting)

        filters_active = (
            bool(query)
            or selected_category != "All Categories"
            or self.global_path_only
        )
        if self.global_path_only and self._global_path_available is False:
            self.filter_status_lbl.setText("(Global critical path unavailable)")
        elif filters_active and self.records:
            self.filter_status_lbl.setText(
                f"(Showing {len(matches)} of {len(self.records)} units)"
            )
        else:
            self.filter_status_lbl.clear()

        if self.table.rowCount() > 0:
            self.table.selectRow(0)
        else:
            self._render_selected_unit_details()


    PHASE_RE = re.compile(
        r"((?:(?:\d+(?:\.\d+)?)(?:h|min|ms|us|µs|s)\s*)+)\s*\(([^)]+)\)"
    )
    TOTAL_RE = re.compile(
        r"=\s*((?:(?:\d+(?:\.\d+)?)(?:h|min|ms|us|µs|s)\s*)+)"
    )
    TARGET_REACHED_RE = re.compile(
        r"([^\s]+\.target)\s+reached\s+after\s+"
        r"((?:(?:\d+(?:\.\d+)?)(?:h|min|ms|us|µs|s)\s*)+)\s+in\s+([^\.\n]+)",
        re.IGNORECASE,
    )
    MILESTONE_TARGETS = (
        "initrd.target",
        "sysinit.target",
        "basic.target",
        "multi-user.target",
        "graphical.target",
        "default.target",
    )
    TIMING_PROPERTIES = (
        "Id",
        "Description",
        "LoadState",
        "ActiveState",
        "SubState",
        "Result",
        "InactiveExitTimestamp",
        "InactiveExitTimestampMonotonic",
        "ActiveEnterTimestamp",
        "ActiveEnterTimestampMonotonic",
        "StateChangeTimestamp",
        "StateChangeTimestampMonotonic",
        "ExecMainStartTimestamp",
        "ExecMainStartTimestampMonotonic",
        "ExecMainExitTimestamp",
        "ExecMainExitTimestampMonotonic",
        "InvocationID",
    )

    def show_unit_critical_path(self):
        if not self.has_scanned:
            QMessageBox.information(self, "Unit Critical Path", "Scan boot timing data first.")
            return
        record = self._selected_record()
        if not record or not record.get("unit"):
            QMessageBox.information(self, "Unit Critical Path", "Select a measured boot unit first.")
            return
        UnitCriticalPathDialog(self, record.get("unit", "")).exec()

    def show_overall_timing(self):
        if not self.has_scanned:
            QMessageBox.information(self, "Overall Timing", "Scan boot timing data first.")
            return
        BootTimingDetailsDialog(self).exec()

    def _update_unit_critical_path_action(self):
        record = self._selected_record()
        enabled = bool(self.has_scanned and record and record.get("unit"))
        self.unit_chain_btn.setEnabled(enabled)

    @classmethod
    def _parse_time_summary(cls, text):
        clean = cls.ANSI_ESCAPE_RE.sub("", text or "")
        phases = {}
        for duration, phase in cls.PHASE_RE.findall(clean):
            phases[str(phase).strip().lower()] = " ".join(duration.split())
        total_match = cls.TOTAL_RE.search(clean)
        target_match = cls.TARGET_REACHED_RE.search(clean)
        return {
            "phases": phases,
            "total": " ".join(total_match.group(1).split()) if total_match else "",
            "target": target_match.group(1).strip() if target_match else "",
            "target_after": " ".join(target_match.group(2).split()) if target_match else "",
            "target_context": target_match.group(3).strip() if target_match else "",
            "raw": clean.strip(),
        }

    @staticmethod
    def _format_monotonic_usec(value):
        try:
            usec = int(str(value or "0").strip())
        except ValueError:
            return "Not reported"
        if usec <= 0:
            return "Not reported"
        seconds = usec / 1_000_000.0
        if seconds < 1:
            return f"+{seconds * 1000:.3f} ms"
        if seconds < 60:
            return f"+{seconds:.3f} s"
        minutes = int(seconds // 60)
        remainder = seconds - (minutes * 60)
        return f"+{minutes} min {remainder:.3f} s"

    def _run_systemctl_show(self, unit_name, properties, timeout=6):
        args = ["systemctl", "show", unit_name, "--no-pager"]
        for prop in properties:
            args.extend(["--property", prop])
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
            env=self._systemd_environment(),
        )
        values = {}
        for line in (result.stdout or "").splitlines():
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
        return values, result

    def _collect_milestones(self):
        if self._milestone_cache is not None:
            return self._milestone_cache
        records = []
        props = (
            "Id",
            "Description",
            "LoadState",
            "ActiveState",
            "SubState",
            "ActiveEnterTimestamp",
            "ActiveEnterTimestampMonotonic",
        )
        for target in self.MILESTONE_TARGETS:
            try:
                values, result = self._run_systemctl_show(target, props, timeout=4)
                error = ""
                if result.returncode != 0:
                    error = (result.stderr or "systemctl show returned a non-zero status.").strip()
            except FileNotFoundError:
                values, error = {}, "systemctl is not available."
            except subprocess.TimeoutExpired:
                values, error = {}, "systemctl show timed out."
            except Exception as exc:
                values, error = {}, f"systemctl show failed: {exc}"
            records.append({"requested": target, "values": values, "error": error})
        self._milestone_cache = records
        return records

    def _selected_record(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 1)
        if item is None:
            return None
        record = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(record, dict):
            return dict(record)
        unit = item.text().strip()
        for candidate in self.records:
            if candidate.get("unit") == unit:
                return dict(candidate)
        return None

    def _unit_timing_values(self, unit_name):
        if unit_name in self._unit_timing_cache:
            return self._unit_timing_cache[unit_name]
        try:
            values, result = self._run_systemctl_show(
                unit_name, self.TIMING_PROPERTIES, timeout=8
            )
            error = ""
            if result.returncode != 0:
                error = (result.stderr or "systemctl show returned a non-zero status.").strip()
        except FileNotFoundError:
            values, error = {}, "systemctl is not available."
        except subprocess.TimeoutExpired:
            values, error = {}, "systemctl show timed out."
        except Exception as exc:
            values, error = {}, f"systemctl show failed: {exc}"
        self._unit_timing_cache[unit_name] = (values, error)
        return values, error

    def _selected_unit_chain(self, unit_name):
        if unit_name in self._unit_chain_cache:
            return self._unit_chain_cache[unit_name]
        try:
            result = self._run_systemd_analyze("critical-chain", unit_name, timeout=12)
            output = result.stdout or result.stderr or ""
            text = self._plain_critical_chain(output)
            if result.returncode != 0 and text:
                text = f"Command exit status: {result.returncode}\n\n{text}"
            elif not text:
                text = "No critical-chain data was returned for this unit."
        except FileNotFoundError:
            text = "systemd-analyze is not available on this system."
        except subprocess.TimeoutExpired:
            text = "Selected-unit critical-chain inspection timed out."
        except Exception as exc:
            text = f"Could not inspect the selected unit critical chain: {exc}"
        self._unit_chain_cache[unit_name] = text
        return text

    def _populate_global_critical_chain_canvas(self, widget):
        _timing_append_heading(widget, "Critical Chain")
        key_format, value_format = _timing_detail_formats()
        cursor = widget.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText("\n", value_format)
        cursor.insertText((self.global_chain_text or "No critical-chain data was returned.").rstrip() + "\n", value_format)
        widget.setTextCursor(cursor)
        _timing_scroll_top(widget)

    def _details_append(self, text):
        cursor = self.details_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(str(text))
        self.details_text.setTextCursor(cursor)

    def _details_key_value(self, key, value):
        shown = str(value) if str(value or "") else "Not reported"
        self._details_append(f"{key}: {shown}\n")

    def _on_unit_selection_changed(self):
        """Render selection immediately, then defer selected-unit timing acquisition."""
        self._detail_debounce_timer.stop()
        self._pending_detail_unit = None
        self._render_selected_unit_details()
        self._update_unit_critical_path_action()

        record = self._selected_record()
        if not record:
            return
        unit = record.get("unit", "")
        if not unit:
            return
        if unit in self._unit_timing_cache:
            return

        self._pending_detail_unit = unit
        self._detail_debounce_timer.start()

    def _launch_pending_unit_details(self):
        """Start one deferred background acquisition for the still-selected unit."""
        unit = self._pending_detail_unit
        self._pending_detail_unit = None
        if not unit:
            return

        record = self._selected_record()
        if not record or record.get("unit", "") != unit:
            return
        if unit in self._unit_timing_cache:
            self._render_selected_unit_details()
            return

        generation = self._details_generation
        if self._detail_inflight.get(unit) == generation:
            return
        self._detail_inflight[unit] = generation

        worker = threading.Thread(
            target=self._collect_unit_details_background,
            args=(generation, unit),
            name=f"boot-timing-details:{unit}",
            daemon=True,
        )
        worker.start()

    def _collect_unit_details_background(self, generation, unit):
        """Collect selected-unit timing metadata away from the Qt GUI thread."""
        try:
            values, result = self._run_systemctl_show(
                unit, self.TIMING_PROPERTIES, timeout=8
            )
            error = ""
            if result.returncode != 0:
                error = (
                    result.stderr or "systemctl show returned a non-zero status."
                ).strip()
        except FileNotFoundError:
            values, error = {}, "systemctl is not available."
        except subprocess.TimeoutExpired:
            values, error = {}, "systemctl show timed out."
        except Exception as exc:
            values, error = {}, f"systemctl show failed: {exc}"

        try:
            self._detail_bridge.ready.emit(generation, unit, values, error)
        except RuntimeError:
            # The widget may have been destroyed while a background query was finishing.
            pass

    def _apply_unit_details_result(self, generation, unit, values, error):
        """Cache background timing results and refresh only if that unit is still selected."""
        if self._detail_inflight.get(unit) == generation:
            self._detail_inflight.pop(unit, None)
        if generation != self._details_generation:
            return

        self._unit_timing_cache[unit] = (dict(values or {}), str(error or ""))

        record = self._selected_record()
        if record and record.get("unit", "") == unit:
            self._render_selected_unit_details()

    def _render_selected_unit_details(self):
        """Render known selection data without ever blocking the GUI thread."""
        self.details_text.clear()
        record = self._selected_record()
        if not record:
            self._details_append("--- Selected Unit ---\n")
            self._details_key_value(
                "Status", "Select a measured boot unit to inspect its timing metadata."
            )
            _timing_scroll_top(self.details_text)
            return

        unit = record.get("unit", "")
        cached_timing = self._unit_timing_cache.get(unit)

        self._details_append("--- Selected Unit Timing ---\n")
        self._details_key_value("Unit", unit)
        self._details_key_value("Category", record.get("category", ""))
        self._details_key_value("Measured Duration (blame)", record.get("duration", ""))

        if cached_timing is None:
            self._details_key_value("Detail Status", "Loading selected-unit timing metadata...")
            _timing_scroll_top(self.details_text)
            return

        values, error = cached_timing
        self._details_key_value("Description", values.get("Description", "Not reported"))
        self._details_key_value("Load State", values.get("LoadState", "Not reported"))
        self._details_key_value("Active State", values.get("ActiveState", "Not reported"))
        self._details_key_value("Sub State", values.get("SubState", "Not reported"))
        self._details_key_value("Result", values.get("Result", "Not reported"))
        self._details_key_value(
            "Activation Start Since Boot",
            self._format_monotonic_usec(values.get("InactiveExitTimestampMonotonic")),
        )
        self._details_key_value(
            "Active Reached Since Boot",
            self._format_monotonic_usec(values.get("ActiveEnterTimestampMonotonic")),
        )
        self._details_key_value(
            "Reported Activation Start",
            values.get("InactiveExitTimestamp", "Not reported"),
        )
        self._details_key_value(
            "Reported Active Reached",
            values.get("ActiveEnterTimestamp", "Not reported"),
        )
        self._details_key_value(
            "State Change", values.get("StateChangeTimestamp", "Not reported")
        )

        if unit.lower().endswith(".service"):
            self._details_append("\n--- Service Process Timing ---\n")
            self._details_key_value(
                "Main Process Started Since Boot",
                self._format_monotonic_usec(values.get("ExecMainStartTimestampMonotonic")),
            )
            self._details_key_value(
                "Reported Main Process Start",
                values.get("ExecMainStartTimestamp", "Not reported"),
            )
            self._details_key_value(
                "Main Process Exit Since Boot",
                self._format_monotonic_usec(values.get("ExecMainExitTimestampMonotonic")),
            )
            self._details_key_value(
                "Reported Main Process Exit",
                values.get("ExecMainExitTimestamp", "Not reported"),
            )

        self._details_append("\n--- Critical-Path Context ---\n")
        if self._global_path_available is True:
            global_path_state = "Yes" if unit and unit in self._global_path_units else "No"
        elif self._global_path_available is False:
            global_path_state = "Unavailable"
        else:
            global_path_state = "Not scanned"
        self._details_key_value(
            "On Reported Global Critical Chain",
            global_path_state,
        )
        self._details_key_value(
            "Invocation ID", values.get("InvocationID", "Not reported")
        )
        if error:
            self._details_key_value("Query Status", error)

        _timing_scroll_top(self.details_text)

    def _populate_boot_phases_canvas(self, widget):
        data = self.phase_data or self._parse_time_summary(self.summary_text)
        phases = data.get("phases", {})
        _timing_append_heading(widget, "Boot Phase Breakdown")
        for phase in ("firmware", "loader", "kernel", "initrd", "userspace"):
            _timing_append_property(widget, phase.title(), phases.get(phase, "Not reported"))
        _timing_append_property(widget, "Total", data.get("total", "Not reported"))

        _timing_append_heading(widget, "Target Reach")
        _timing_append_property(widget, "Target", data.get("target", "Not reported"))
        _timing_append_property(widget, "Reached After", data.get("target_after", "Not reported"))
        _timing_append_property(widget, "Timing Context", data.get("target_context", "Not reported"))

        _timing_append_heading(widget, "Reported Summary")
        _timing_append_property(widget, "systemd-analyze time", self._one_line(data.get("raw", "")))
        _timing_scroll_top(widget)

    def _populate_milestones_canvas(self, widget):
        _timing_append_heading(widget, "Target Milestones")
        _timing_append_property(
            widget,
            "Interpretation",
            "Reached values are systemd-reported ActiveEnterTimestampMonotonic offsets from boot; targets that are absent or never entered active state are not inferred.",
        )
        for record in self._collect_milestones():
            requested = record["requested"]
            values = record["values"]
            _timing_append_heading(widget, requested)
            _timing_append_property(widget, "Reported Id", values.get("Id", "Not reported"))
            _timing_append_property(widget, "Description", values.get("Description", "Not reported"))
            _timing_append_property(widget, "Load State", values.get("LoadState", "Not reported"))
            _timing_append_property(widget, "Active State", values.get("ActiveState", "Not reported"))
            _timing_append_property(widget, "Sub State", values.get("SubState", "Not reported"))
            _timing_append_property(
                widget,
                "Reached Since Boot",
                self._format_monotonic_usec(values.get("ActiveEnterTimestampMonotonic")),
            )
            _timing_append_property(widget, "Reported Reached Time", values.get("ActiveEnterTimestamp", "Not reported"))
            if record["error"]:
                _timing_append_property(widget, "Query Status", record["error"])
        _timing_scroll_top(widget)

    def _phase_breakdown_export_text(self):
        data = self.phase_data or self._parse_time_summary(self.summary_text)
        phases = data.get("phases", {})
        lines = ["Boot Phase Breakdown"]
        for phase in ("firmware", "loader", "kernel", "initrd", "userspace"):
            lines.append(f"{phase.title()}: {phases.get(phase, 'Not reported')}")
        lines.append(f"Total: {data.get('total') or 'Not reported'}")
        lines.append("")
        lines.append("Target Reach")
        lines.append(f"Target: {data.get('target') or 'Not reported'}")
        lines.append(f"Reached After: {data.get('target_after') or 'Not reported'}")
        lines.append(f"Timing Context: {data.get('target_context') or 'Not reported'}")
        return "\n".join(lines)

    def _milestones_export_text(self):
        lines = []
        for record in self._collect_milestones():
            values = record["values"]
            lines.append(record["requested"])
            lines.append(f"  Reported Id: {values.get('Id') or 'Not reported'}")
            lines.append(f"  Description: {values.get('Description') or 'Not reported'}")
            lines.append(f"  Active State: {values.get('ActiveState') or 'Not reported'}")
            lines.append(f"  Sub State: {values.get('SubState') or 'Not reported'}")
            lines.append(
                "  Reached Since Boot: "
                + self._format_monotonic_usec(values.get("ActiveEnterTimestampMonotonic"))
            )
            if record["error"]:
                lines.append(f"  Query Status: {record['error']}")
            lines.append("")
        return "\n".join(lines).rstrip()


    def _finish_scan_button(self):
        self.refresh_btn.setText("Scan Again")
        self.refresh_btn.setEnabled(True)

    @staticmethod
    def _one_line(text):
        return " ".join(str(text or "").split())

    def load_boot_data(self):
        self.refresh_btn.setText("Scanning...")
        self.refresh_btn.setEnabled(False)
        self.has_scanned = False
        self.records = []
        self.phase_data = {}
        self._milestone_cache = None
        self._details_generation += 1
        self._detail_debounce_timer.stop()
        self._pending_detail_unit = None
        self._detail_inflight = {}
        self._unit_timing_cache = {}
        self._unit_chain_cache = {}
        self._global_path_units = set()
        self._global_path_available = None
        self.overall_timing_btn.setEnabled(False)
        self.unit_chain_btn.setEnabled(False)
        self.table.setRowCount(0)
        self.global_chain_text = "Reading boot critical-chain data..."
        self.details_text.clear()
        self.details_text.setPlainText("Scan in progress...")
        self.summary_text = "Reading boot timing data..."
        self.status_summary_text = "Inspecting current boot..."
        self.status_lbl.setText(self.status_summary_text)
        QApplication.processEvents()

        try:
            time_result = self._run_systemd_analyze("time")
            blame_result = self._run_systemd_analyze("blame", timeout=12)
            chain_result = self._run_systemd_analyze("critical-chain", timeout=12)
        except FileNotFoundError:
            self.summary_text = "systemd-analyze is not available on this system."
            self.global_chain_text = "Boot critical-chain data is unavailable."
            self.stats_label.setText("Measured Boot Units: 0")
            self.status_summary_text = "systemd-analyze command unavailable."
            self.status_lbl.setText(self.status_summary_text)
            self.details_text.setPlainText("Boot timing data is unavailable.")
            self._finish_scan_button()
            return
        except subprocess.TimeoutExpired:
            self.summary_text = "Boot inspection timed out."
            self.global_chain_text = "Boot critical-chain data could not be read within the time limit."
            self.stats_label.setText("Measured Boot Units: 0")
            self.status_summary_text = "Timed out while inspecting boot data."
            self.status_lbl.setText(self.status_summary_text)
            self.details_text.setPlainText("Boot timing inspection timed out.")
            self._finish_scan_button()
            return
        except Exception as exc:
            self.summary_text = f"Boot timing data unavailable: {exc}"
            self.global_chain_text = "Boot critical-chain data is unavailable."
            self.stats_label.setText("Measured Boot Units: 0")
            self.status_summary_text = "Could not inspect boot data."
            self.status_lbl.setText(self.status_summary_text)
            self.details_text.setPlainText("Boot timing data could not be inspected.")
            self._finish_scan_button()
            return

        summary = (time_result.stdout or time_result.stderr or "").strip()
        if summary:
            self.summary_text = self.ANSI_ESCAPE_RE.sub("", summary)
        else:
            self.summary_text = "No boot timing summary was returned."
        self.phase_data = self._parse_time_summary(self.summary_text)

        blame_output = blame_result.stdout or ""
        self.records = self._parse_blame(blame_output)
        self.stats_label.setText(f"Measured Boot Units: {len(self.records)}")

        chain_output = chain_result.stdout or chain_result.stderr or ""
        plain_chain = self._plain_critical_chain(chain_output)
        self.global_chain_text = plain_chain if plain_chain else "No critical-chain data was returned."
        self._global_path_available = chain_result.returncode == 0
        self._global_path_units = self._global_path_unit_names(chain_output) if self._global_path_available else set()
        self.filter_units()

        failures = []
        if time_result.returncode != 0:
            failures.append("summary")
        if blame_result.returncode != 0:
            failures.append("slow-unit list")
        if chain_result.returncode != 0:
            failures.append("critical chain")

        if failures:
            suffix = "Boot inspection completed with unavailable data: " + ", ".join(failures) + "."
            self.status_summary_text = self._one_line(self.summary_text + "  " + suffix)
            self.status_lbl.setText(self.status_summary_text)
        else:
            self.status_summary_text = self._one_line(self.summary_text)
            self.status_lbl.setText(self.status_summary_text)
        self.has_scanned = True
        self.overall_timing_btn.setEnabled(True)
        self._update_unit_critical_path_action()
        self._finish_scan_button()

def create_applet(parent=None):
    return BootTimingWidget(parent=parent)

def run_standalone():
    import sys
    from pathlib import Path
    from PyQt6.QtGui import QIcon
    from PyQt6.QtWidgets import QApplication, QMainWindow
    from ._support import STANDALONE_STYLESHEET
    app = QApplication(sys.argv)
    app.setApplicationName(APPLET_NAME)
    app.setOrganizationName(APPLET_AUTHOR)
    icon_path = Path(__file__).resolve().parent / "icon.png"
    if icon_path.is_file():
        app.setWindowIcon(QIcon(str(icon_path)))
    app.setStyleSheet(STANDALONE_STYLESHEET)
    window = QMainWindow()
    if icon_path.is_file():
        window.setWindowIcon(QIcon(str(icon_path)))
    window.setWindowTitle(f"{APPLET_NAME} {APPLET_VERSION} — LinSpectacles Applet")
    window.resize(1200, 780)
    window.setCentralWidget(create_applet())
    window.show()
    return app.exec()
