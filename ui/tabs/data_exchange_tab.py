# -*- coding: utf-8 -*-
"""Excel-first Data Exchange with a safe Preview → Validate → Import workflow."""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from collections.abc import Mapping

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QCursor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from services.data_exchange_service import DataExchangeService


logger = logging.getLogger(__name__)


class DataExchangeTab(QWidget):
    """
    Safe Excel/Data Exchange UI.

    Required DataExchangeService methods:
        model_names()
        preview_excel(path, model_name, update_existing)
        import_preview_rows(rows, update_existing)
        create_template(model_name, path)
        create_master_template(path)
        export_model(model_name, path, fmt)
        export_pack(path)
    """

    data_imported = pyqtSignal(dict)

    EXPORT_FORMATS = {
        "xlsx": "Excel workbook (*.xlsx)",
        "csv": "CSV file (*.csv)",
        "json": "JSON file (*.json)",
        "html": "HTML report (*.html)",
    }

    STATUS_COLORS = {
        "NEW": "#dff5e3",
        "CREATE": "#dff5e3",
        "INSERT": "#dff5e3",
        "UPDATE": "#fff0c2",
        "ERROR": "#ffd9d9",
        "INVALID": "#ffd9d9",
        "DUPLICATE": "#ffe4bf",
        "SKIP": "#e8edf1",
        "SKIPPED": "#e8edf1",
    }

    SUMMARY_STYLES = {
        "info": (
            "#eef6fb",
            "#c9dfec",
            "#123047",
        ),
        "success": (
            "#e9f8ed",
            "#b9dfc2",
            "#175c2c",
        ),
        "warning": (
            "#fff8e1",
            "#eed694",
            "#725400",
        ),
        "error": (
            "#fdecec",
            "#efb7b7",
            "#8a1f1f",
        ),
    }

    def __init__(self, db, session):
        super().__init__()

        self.db = db
        self.session = session
        self.svc = DataExchangeService(db)

        self.preview_rows = []
        self.current_file = None

        # (model_name, update_existing)
        self._preview_context = None
        self._preview_imported = False
        self._valid_row_count = 0

        self._busy = False
        self._cursor_overridden = False

        self._build()
        self.refresh()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(10)

        title = QLabel("⇄ Excel / Data Exchange Center")
        title.setStyleSheet(
            "font-size:24px;"
            "font-weight:800;"
            "color:#123047;"
        )
        root.addWidget(title)

        description = QLabel(
            "Safe workflow: Select Excel → Analyze → Preview errors and "
            "duplicates → Import valid records. No database changes are "
            "made during analysis."
        )
        description.setWordWrap(True)
        description.setTextFormat(Qt.TextFormat.PlainText)
        root.addWidget(description)

        # -------------------- Import section --------------------

        import_box = QGroupBox("1) Import Wizard")
        import_grid = QGridLayout(import_box)
        import_grid.setColumnStretch(1, 1)

        self.model = QComboBox()
        self.model.setMinimumWidth(220)

        import_grid.addWidget(QLabel("Data type"), 0, 0)
        import_grid.addWidget(self.model, 0, 1)

        # Do not call this self.update because QWidget already has update().
        self.update_existing_checkbox = QCheckBox(
            "Update existing records by natural key"
        )
        self.update_existing_checkbox.setChecked(True)
        import_grid.addWidget(
            self.update_existing_checkbox,
            0,
            2,
            1,
            3,
        )

        self.analyze_button = QPushButton("📂 Select Excel & Analyze")
        self.analyze_button.clicked.connect(self.analyze)
        import_grid.addWidget(self.analyze_button, 1, 0)

        self.import_button = QPushButton("✓ Import Valid Records")
        self.import_button.setStyleSheet("font-weight:700;")
        self.import_button.clicked.connect(self.import_valid)
        import_grid.addWidget(self.import_button, 1, 1)

        self.template_button = QPushButton("Download Template")
        self.template_button.clicked.connect(self.template)
        import_grid.addWidget(self.template_button, 1, 2)

        self.master_template_button = QPushButton("Master Excel Template")
        self.master_template_button.clicked.connect(self.master_template)
        import_grid.addWidget(self.master_template_button, 1, 3)

        self.clear_button = QPushButton("Clear Preview")
        self.clear_button.clicked.connect(
            lambda _checked=False: self.clear_preview()
        )
        import_grid.addWidget(self.clear_button, 1, 4)

        root.addWidget(import_box)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        root.addWidget(self.progress)

        self.summary = QLabel(
            "Ready. Analysis is read-only until you press "
            "Import Valid Records."
        )
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
        self.summary.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        root.addWidget(self.summary)
        self._set_summary(self.summary.text(), "info")

        self.preview = QTableWidget()
        self.preview.setColumnCount(5)
        self.preview.setHorizontalHeaderLabels(
            [
                "Sheet",
                "Row",
                "Status",
                "Errors",
                "Data Preview",
            ]
        )
        self.preview.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.preview.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.preview.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.preview.setAlternatingRowColors(True)
        self.preview.setSortingEnabled(True)
        self.preview.setWordWrap(False)
        self.preview.verticalHeader().setVisible(False)
        self.preview.setHorizontalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerPixel
        )
        self.preview.setVerticalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerPixel
        )

        header = self.preview.horizontalHeader()
        header.setMinimumSectionSize(70)
        header.setSectionResizeMode(
            0,
            QHeaderView.ResizeMode.ResizeToContents,
        )
        header.setSectionResizeMode(
            1,
            QHeaderView.ResizeMode.ResizeToContents,
        )
        header.setSectionResizeMode(
            2,
            QHeaderView.ResizeMode.ResizeToContents,
        )
        header.setSectionResizeMode(
            3,
            QHeaderView.ResizeMode.Stretch,
        )
        header.setSectionResizeMode(
            4,
            QHeaderView.ResizeMode.Stretch,
        )

        root.addWidget(self.preview, 1)

        # -------------------- Export section --------------------

        export_box = QGroupBox("2) Export")
        export_grid = QGridLayout(export_box)
        export_grid.setColumnStretch(1, 1)

        self.exp_model = QComboBox()
        self.exp_model.setMinimumWidth(220)

        export_grid.addWidget(QLabel("Data type"), 0, 0)
        export_grid.addWidget(self.exp_model, 0, 1)

        export_definitions = [
            ("Excel (.xlsx)", "xlsx"),
            ("CSV (.csv)", "csv"),
            ("JSON (.json)", "json"),
            ("HTML Report", "html"),
        ]

        self.export_buttons = []

        for column, (label, fmt) in enumerate(
            export_definitions,
            start=2,
        ):
            button = QPushButton(label)
            button.clicked.connect(
                lambda _checked=False, export_format=fmt: (
                    self.export_one(export_format)
                )
            )
            export_grid.addWidget(button, 0, column)
            self.export_buttons.append(button)

        self.export_pack_button = QPushButton("Full Project Excel Pack")
        self.export_pack_button.clicked.connect(self.export_pack)
        export_grid.addWidget(self.export_pack_button, 1, 0, 1, 2)

        root.addWidget(export_box)

        # Changing these values invalidates the previous analysis.
        self.model.currentTextChanged.connect(
            self._on_preview_context_changed
        )
        self.update_existing_checkbox.toggled.connect(
            self._on_preview_context_changed
        )

        self._update_controls()

    # ------------------------------------------------------------------
    # General UI helpers
    # ------------------------------------------------------------------

    def _set_summary(self, text, level="info"):
        background, border, color = self.SUMMARY_STYLES.get(
            level,
            self.SUMMARY_STYLES["info"],
        )

        self.summary.setText(str(text))
        self.summary.setStyleSheet(
            "QLabel {"
            f"background:{background};"
            f"border:1px solid {border};"
            f"color:{color};"
            "padding:10px;"
            "border-radius:6px;"
            "}"
        )

    def _start_busy(self, message):
        if self._busy:
            return False

        self._busy = True
        self.progress.setRange(0, 0)
        self._set_summary(message, "info")
        self._update_controls()

        if QApplication.instance() is not None:
            QApplication.setOverrideCursor(
                QCursor(Qt.CursorShape.WaitCursor)
            )
            self._cursor_overridden = True
            QApplication.processEvents()

        return True

    def _finish_busy(self, success):
        self._busy = False

        self.progress.setRange(0, 100)
        self.progress.setValue(100 if success else 0)

        if self._cursor_overridden:
            QApplication.restoreOverrideCursor()
            self._cursor_overridden = False

        self._update_controls()

    def _update_controls(self):
        active = not self._busy
        has_import_model = bool(self.model.currentText().strip())
        has_export_model = bool(self.exp_model.currentText().strip())
        has_any_model = self.model.count() > 0

        self.model.setEnabled(active and self.model.count() > 0)
        self.update_existing_checkbox.setEnabled(
            active and has_import_model
        )

        self.analyze_button.setEnabled(
            active and has_import_model
        )
        self.template_button.setEnabled(
            active and has_import_model
        )
        self.master_template_button.setEnabled(
            active and has_any_model
        )

        self.import_button.setEnabled(
            active and self._can_import()
        )
        self.clear_button.setEnabled(
            active
            and (
                bool(self.preview_rows)
                or self.current_file is not None
            )
        )

        self.exp_model.setEnabled(
            active and self.exp_model.count() > 0
        )

        for button in self.export_buttons:
            button.setEnabled(active and has_export_model)

        self.export_pack_button.setEnabled(
            active and has_any_model
        )

    def _current_preview_context(self):
        return (
            self.model.currentText(),
            bool(self.update_existing_checkbox.isChecked()),
        )

    def _can_import(self):
        return bool(
            self.preview_rows
            and self._valid_row_count > 0
            and not self._preview_imported
            and self._preview_context
            == self._current_preview_context()
        )

    def _on_preview_context_changed(self, *_args):
        if self._busy:
            return

        if self.preview_rows or self.current_file is not None:
            self._clear_preview(show_message=False)
            self._set_summary(
                "The previous preview was cleared because the data type "
                "or update policy changed. Analyze the Excel file again.",
                "warning",
            )

    def clear_preview(self):
        self._clear_preview(show_message=True)

    def _clear_preview(self, show_message=False):
        self.preview_rows = []
        self.current_file = None
        self._preview_context = None
        self._preview_imported = False
        self._valid_row_count = 0

        self.preview.setSortingEnabled(False)
        self.preview.clearContents()
        self.preview.setRowCount(0)
        self.preview.setSortingEnabled(True)

        if not self._busy:
            self.progress.setRange(0, 100)
            self.progress.setValue(0)

        if show_message:
            self._set_summary(
                "Preview cleared. Select an Excel file to analyze.",
                "info",
            )

        self._update_controls()

    # ------------------------------------------------------------------
    # Model list
    # ------------------------------------------------------------------

    def refresh(self):
        """Reload model names without discarding a valid preview unnecessarily."""
        if self._busy:
            return

        previous_import_model = self.model.currentText()
        previous_export_model = self.exp_model.currentText()

        try:
            raw_names = self.svc.model_names()

            if raw_names is None:
                raw_names = []
            elif isinstance(raw_names, str):
                raw_names = [raw_names]

            names = []
            seen = set()

            for value in raw_names:
                name = str(value).strip()

                if not name or name in seen:
                    continue

                seen.add(name)
                names.append(name)

            self._replace_combo_items(
                self.model,
                names,
                previous_import_model,
            )
            self._replace_combo_items(
                self.exp_model,
                names,
                previous_export_model,
            )

            if (
                self.current_file is not None
                and self._preview_context
                != self._current_preview_context()
            ):
                self._clear_preview(show_message=False)
                self._set_summary(
                    "The preview was cleared because its data model "
                    "is no longer selected.",
                    "warning",
                )

        except Exception as exc:
            logger.exception("Could not load data exchange model names")
            self._set_summary(
                f"Could not load data types: "
                f"{self._exception_text(exc)}",
                "error",
            )

        self._update_controls()

    @staticmethod
    def _replace_combo_items(combo, names, previous_value):
        previous_signal_state = combo.blockSignals(True)

        try:
            combo.clear()
            combo.addItems(names)

            index = combo.findText(previous_value)

            if index >= 0:
                combo.setCurrentIndex(index)
            elif combo.count() > 0:
                combo.setCurrentIndex(0)
            else:
                combo.setCurrentIndex(-1)
        finally:
            combo.blockSignals(previous_signal_state)

    # ------------------------------------------------------------------
    # Excel analysis
    # ------------------------------------------------------------------

    def analyze(self):
        model_name = self.model.currentText()

        if not model_name.strip():
            QMessageBox.warning(
                self,
                "Analysis",
                "No data type is available for analysis.",
            )
            return

        path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Select Excel for Validation",
            "",
            "Excel workbook (*.xlsx *.xlsm)",
        )

        if not path:
            return

        # Clear only after the user has actually selected a file.
        self._clear_preview(show_message=False)

        if not self._start_busy(
            "Analyzing the Excel file. No database changes are being made..."
        ):
            return

        success = False
        error_message = None

        try:
            context = (
                model_name,
                bool(self.update_existing_checkbox.isChecked()),
            )

            raw_rows = self.svc.preview_excel(
                path,
                model_name=model_name,
                update_existing=context[1],
            )

            if raw_rows is None:
                raw_rows = []

            if isinstance(raw_rows, Mapping):
                raise TypeError(
                    "preview_excel() must return a collection of rows, "
                    "not a single mapping."
                )

            normalized_rows = []

            for index, row in enumerate(raw_rows, start=1):
                if not isinstance(row, Mapping):
                    raise TypeError(
                        f"Preview item {index} is invalid. "
                        "Each preview row must be a mapping/dictionary."
                    )

                normalized_rows.append(dict(row))

            # Protect against programmatic UI changes during analysis.
            if context != self._current_preview_context():
                raise RuntimeError(
                    "Import settings changed during analysis. "
                    "Please analyze the file again."
                )

            self.preview_rows = normalized_rows
            self.current_file = path
            self._preview_context = context
            self._preview_imported = False
            self._valid_row_count = sum(
                1
                for row in self.preview_rows
                if not self._row_has_errors(row)
            )

            self._populate_preview_table()

            summary_text, error_count = self._analysis_summary(path)

            if not self.preview_rows or error_count > 0:
                summary_level = "warning"
            else:
                summary_level = "success"

            self._set_summary(summary_text, summary_level)
            success = True

        except Exception as exc:
            logger.exception("Excel analysis failed")
            error_message = self._exception_text(exc)

            self._clear_preview(show_message=False)
            self._set_summary(
                f"Analysis failed: {error_message}",
                "error",
            )

        finally:
            self._finish_busy(success)

        if error_message:
            QMessageBox.critical(
                self,
                "Analysis failed",
                error_message,
            )

    def _populate_preview_table(self):
        sorting_was_enabled = self.preview.isSortingEnabled()

        self.preview.setSortingEnabled(False)
        self.preview.setUpdatesEnabled(False)
        self.preview.clearContents()
        self.preview.setRowCount(len(self.preview_rows))

        try:
            for table_row, preview_row in enumerate(self.preview_rows):
                error_text = self._row_error_text(preview_row)

                original_status = self._cell_text(
                    preview_row.get("status")
                ).strip().upper()

                if error_text:
                    display_status = "ERROR"
                else:
                    display_status = original_status or "NEW"

                sheet_text = self._cell_text(
                    preview_row.get("sheet")
                )
                excel_row = preview_row.get("row", "")
                serialized_data = self._serialize_data(
                    preview_row.get("data", {})
                )

                sheet_item = QTableWidgetItem(sheet_text)

                row_item = QTableWidgetItem()
                try:
                    row_item.setData(
                        Qt.ItemDataRole.DisplayRole,
                        int(excel_row),
                    )
                except (TypeError, ValueError):
                    row_item.setText(self._cell_text(excel_row))

                row_item.setTextAlignment(
                    Qt.AlignmentFlag.AlignCenter
                )

                status_item = QTableWidgetItem(display_status)
                status_item.setTextAlignment(
                    Qt.AlignmentFlag.AlignCenter
                )

                if error_text and original_status:
                    status_item.setToolTip(
                        f"Original status: {original_status}"
                    )

                status_color = self.STATUS_COLORS.get(
                    display_status,
                    "#ffffff",
                )
                status_item.setBackground(
                    QBrush(QColor(status_color))
                )

                error_item = QTableWidgetItem(
                    self._clip(error_text, 500)
                )
                if error_text:
                    error_item.setToolTip(
                        self._clip(error_text, 4000)
                    )
                    error_item.setForeground(
                        QBrush(QColor("#9b1c1c"))
                    )

                data_item = QTableWidgetItem(
                    self._clip(serialized_data, 700)
                )
                data_item.setToolTip(
                    self._clip(serialized_data, 4000)
                )

                items = [
                    sheet_item,
                    row_item,
                    status_item,
                    error_item,
                    data_item,
                ]

                for column, item in enumerate(items):
                    self.preview.setItem(
                        table_row,
                        column,
                        item,
                    )

        finally:
            self.preview.setUpdatesEnabled(True)
            self.preview.setSortingEnabled(
                sorting_was_enabled
            )

    def _analysis_summary(self, path):
        total_count = len(self.preview_rows)
        error_count = total_count - self._valid_row_count
        status_counts = Counter()

        for row in self.preview_rows:
            if self._row_has_errors(row):
                continue

            status = self._cell_text(
                row.get("status")
            ).strip().upper()

            status_counts[status or "NEW"] += 1

        new_count = status_counts.pop("NEW", 0)
        update_count = status_counts.pop("UPDATE", 0)

        parts = [
            f"Analyzed: {total_count}",
            f"Valid: {self._valid_row_count}",
            f"NEW: {new_count}",
            f"UPDATE: {update_count}",
            f"ERRORS: {error_count}",
        ]

        for status, count in sorted(status_counts.items()):
            parts.append(f"{status}: {count}")

        return (
            " | ".join(parts)
            + f"\nFile: {path}"
            + "\nOnly rows without validation errors will be sent "
              "to the import service.",
            error_count,
        )

    # ------------------------------------------------------------------
    # Import
    # ------------------------------------------------------------------

    def import_valid(self):
        if not self.preview_rows:
            QMessageBox.warning(
                self,
                "Import",
                "Analyze an Excel file first.",
            )
            return

        if self._preview_imported:
            QMessageBox.warning(
                self,
                "Import",
                "This preview has already been used for an import attempt. "
                "Analyze the file again before importing.",
            )
            return

        if self._preview_context != self._current_preview_context():
            self._clear_preview(show_message=False)
            self._set_summary(
                "The import settings changed. Analyze the Excel file again.",
                "warning",
            )
            QMessageBox.warning(
                self,
                "Import",
                "The import settings no longer match the preview. "
                "Analyze the file again.",
            )
            return

        valid_count = self._valid_row_count

        if valid_count <= 0:
            QMessageBox.warning(
                self,
                "Import",
                "No valid rows are available.",
            )
            return

        answer = QMessageBox.question(
            self,
            "Confirm Import",
            f"Import {valid_count} valid rows?\n\n"
            "Rows containing validation errors will not be imported.",
            (
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No
            ),
            QMessageBox.StandardButton.No,
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        if not self._start_busy(
            f"Importing {valid_count} valid rows..."
        ):
            return

        success = False
        error_message = None
        result_payload = None
        result_errors = []
        attempted = False

        try:
            attempted = True

            result = self.svc.import_preview_rows(
                self.preview_rows,
                self._preview_context[1],
            )

            if not isinstance(result, Mapping):
                raise TypeError(
                    "import_preview_rows() returned an invalid result. "
                    "A dictionary/mapping was expected."
                )

            # Prevent accidental second import using the same preview.
            self._preview_imported = True

            created = self._count_value(
                result.get("created", 0)
            )
            updated = self._count_value(
                result.get("updated", 0)
            )
            skipped = self._count_value(
                result.get("skipped", 0)
            )
            result_errors = self._message_list(
                result.get("errors")
            )

            result_payload = dict(result)
            result_payload.setdefault(
                "model_name",
                self._preview_context[0],
            )

            summary_text = (
                "Import complete: "
                f"created={created} | "
                f"updated={updated} | "
                f"skipped={skipped} | "
                f"errors={len(result_errors)}"
                "\nAnalyze the file again before starting another import."
            )

            self._set_summary(
                summary_text,
                "warning" if result_errors else "success",
            )
            success = True

        except Exception as exc:
            logger.exception("Import failed")
            error_message = self._exception_text(exc)

            # The service may have partially reached the database before
            # raising. Re-analysis is therefore safer than blind retry.
            if attempted:
                self._preview_imported = True

            self._set_summary(
                f"Import failed: {error_message}\n"
                "For safety, analyze the Excel file again before retrying.",
                "error",
            )

        finally:
            self._finish_busy(success)

        if error_message:
            QMessageBox.critical(
                self,
                "Import failed",
                error_message
                + "\n\nAnalyze the Excel file again before retrying.",
            )
            return

        if result_errors:
            shown_errors = result_errors[:15]
            remaining_count = len(result_errors) - len(shown_errors)

            message = "\n".join(shown_errors)

            if remaining_count > 0:
                message += (
                    f"\n\n... and {remaining_count} more error(s)."
                )

            QMessageBox.warning(
                self,
                "Import completed with warnings",
                message,
            )
        else:
            QMessageBox.information(
                self,
                "Import complete",
                "All valid rows were imported successfully.",
            )

        if result_payload is not None:
            self.data_imported.emit(result_payload)

    # ------------------------------------------------------------------
    # Templates
    # ------------------------------------------------------------------

    def template(self):
        model_name = self.model.currentText()

        if not model_name.strip():
            QMessageBox.warning(
                self,
                "Template",
                "No data type is selected.",
            )
            return

        default_name = (
            f"{self._safe_filename(model_name, 'data')}_template.xlsx"
        )

        path, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Save Excel Template",
            default_name,
            "Excel workbook (*.xlsx)",
        )

        if not path:
            return

        path = self._ensure_extension(path, "xlsx")

        self._run_file_action(
            operation_title="Template",
            busy_message="Creating the Excel template...",
            success_message=f"Template created:\n{path}",
            action=lambda: self.svc.create_template(
                model_name,
                path,
            ),
            show_success_dialog=True,
        )

    def master_template(self):
        path, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Save Master Template",
            "PipeAgent_Master_Import_Template.xlsx",
            "Excel workbook (*.xlsx)",
        )

        if not path:
            return

        path = self._ensure_extension(path, "xlsx")

        self._run_file_action(
            operation_title="Master Template",
            busy_message="Creating the master Excel template...",
            success_message=f"Master template created:\n{path}",
            action=lambda: self.svc.create_master_template(path),
            show_success_dialog=True,
        )

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_one(self, fmt):
        fmt = str(fmt).strip().lower()

        if fmt not in self.EXPORT_FORMATS:
            QMessageBox.critical(
                self,
                "Export",
                f"Unsupported export format: {fmt}",
            )
            return

        model_name = self.exp_model.currentText()

        if not model_name.strip():
            QMessageBox.warning(
                self,
                "Export",
                "No data type is selected.",
            )
            return

        default_name = (
            f"{self._safe_filename(model_name, 'data')}.{fmt}"
        )

        path, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export",
            default_name,
            self.EXPORT_FORMATS[fmt],
        )

        if not path:
            return

        path = self._ensure_extension(path, fmt)

        self._run_file_action(
            operation_title="Export",
            busy_message=(
                f"Exporting {model_name} as {fmt.upper()}..."
            ),
            success_message=(
                f"Exported {model_name} → {path}"
            ),
            action=lambda: self.svc.export_model(
                model_name,
                path,
                fmt,
            ),
            show_success_dialog=False,
        )

    def export_pack(self):
        path, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Full Project Excel Pack",
            "PipeAgent_Project_Export.xlsx",
            "Excel workbook (*.xlsx)",
        )

        if not path:
            return

        path = self._ensure_extension(path, "xlsx")

        self._run_file_action(
            operation_title="Project Export",
            busy_message="Creating the full project Excel pack...",
            success_message=(
                f"Full project pack exported → {path}"
            ),
            action=lambda: self.svc.export_pack(path),
            show_success_dialog=False,
        )

    # ------------------------------------------------------------------
    # Service operation helper
    # ------------------------------------------------------------------

    def _run_file_action(
        self,
        operation_title,
        busy_message,
        success_message,
        action,
        show_success_dialog=False,
    ):
        if not self._start_busy(busy_message):
            return False

        success = False
        error_message = None

        try:
            action()
            self._set_summary(success_message, "success")
            success = True

        except Exception as exc:
            logger.exception("%s failed", operation_title)
            error_message = self._exception_text(exc)

            self._set_summary(
                f"{operation_title} failed: {error_message}",
                "error",
            )

        finally:
            self._finish_busy(success)

        if error_message:
            QMessageBox.critical(
                self,
                f"{operation_title} failed",
                error_message,
            )
            return False

        if show_success_dialog:
            QMessageBox.information(
                self,
                operation_title,
                success_message,
            )

        return True

    # ------------------------------------------------------------------
    # Data formatting helpers
    # ------------------------------------------------------------------

    @classmethod
    def _row_has_errors(cls, row):
        return bool(cls._row_error_text(row))

    @classmethod
    def _row_error_text(cls, row):
        if not isinstance(row, Mapping):
            return "Invalid preview row."

        return "\n".join(
            cls._message_list(row.get("errors"))
        ).strip()

    @classmethod
    def _message_list(cls, value):
        if value is None or value is False:
            return []

        if isinstance(value, str):
            text = value.strip()
            return [text] if text else []

        if isinstance(value, Mapping):
            if not value:
                return []
            return [cls._serialize_data(value)]

        if isinstance(value, (list, tuple, set)):
            messages = []

            for item in value:
                messages.extend(cls._message_list(item))

            return messages

        if isinstance(value, (int, float)) and value == 0:
            return []

        text = str(value).strip()
        return [text] if text else []

    @staticmethod
    def _serialize_data(value):
        try:
            return json.dumps(
                value,
                ensure_ascii=False,
                default=str,
                sort_keys=True,
            )
        except Exception:
            try:
                return str(value)
            except Exception:
                return "<unprintable data>"

    @staticmethod
    def _cell_text(value):
        return "" if value is None else str(value)

    @staticmethod
    def _clip(value, limit):
        text = "" if value is None else str(value)

        if len(text) <= limit:
            return text

        if limit <= 1:
            return text[:limit]

        return text[: limit - 1] + "…"

    @staticmethod
    def _safe_filename(value, fallback="file"):
        name = str(value).strip()
        name = re.sub(r'[\\/:*?"<>|]+', "_", name)
        name = re.sub(r"\s+", "_", name)
        name = name.strip("._ ")

        return name or fallback

    @staticmethod
    def _ensure_extension(path, extension):
        extension = str(extension).lower().lstrip(".")
        expected_suffix = f".{extension}"

        if not str(path).lower().endswith(expected_suffix):
            return f"{path}{expected_suffix}"

        return path

    @staticmethod
    def _count_value(value):
        if value is None:
            return 0

        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _exception_text(exc):
        text = str(exc).strip()
        return text or exc.__class__.__name__