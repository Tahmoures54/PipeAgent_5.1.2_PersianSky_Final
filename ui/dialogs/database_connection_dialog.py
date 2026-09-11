# -*- coding: utf-8 -*-
"""Choose the local SQLite file or a shared PostgreSQL / SQL Server database."""

from __future__ import annotations

import logging
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from config import CONNECTION_PROFILE_PATH, DATABASE_PATH, DATABASE_URL_LOCKED_BY_ENV
from db.connection_profiles import (
    ENGINE_MSSQL,
    ENGINE_POSTGRESQL,
    ENGINE_SQLITE,
    ConnectionProfile,
    build_url,
    describe_database_target,
    load_profile,
    odbc_driver_names,
    profile_from_mapping,
    save_profile,
    test_database_url,
)

logger = logging.getLogger(__name__)


class DatabaseConnectionDialog(QDialog):
    """Site-admin connection target: SQLite, PostgreSQL, or SQL Server / Express."""

    def __init__(self, parent: QWidget | None = None, *, startup_error: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle("Database Connection")
        self.setMinimumWidth(560)
        self.setModal(True)
        self._saved = False

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setSizeConstraint(QVBoxLayout.SizeConstraint.SetFixedSize)

        intro = QLabel(
            "SQLite is for one workstation. Several users on one project need a "
            "shared server: SQL Server Express on the site LAN, or PostgreSQL "
            "(office or online)."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        if DATABASE_URL_LOCKED_BY_ENV:
            lock = QLabel(
                "PIPEAGENT_DATABASE_URL is set in the environment. "
                "That value is used at startup and overrides this profile."
            )
            lock.setWordWrap(True)
            lock.setStyleSheet("color:#92400e; background:#fef3c7; padding:8px; border-radius:6px;")
            layout.addWidget(lock)

        if startup_error:
            err = QLabel(startup_error)
            err.setWordWrap(True)
            err.setStyleSheet("color:#991b1b; background:#fee2e2; padding:8px; border-radius:6px;")
            layout.addWidget(err)

        self.engine = QComboBox()
        self.engine.addItem("Local SQLite (single workstation)", ENGINE_SQLITE)
        self.engine.addItem("SQL Server / Express (site server)", ENGINE_MSSQL)
        self.engine.addItem("PostgreSQL (LAN or online)", ENGINE_POSTGRESQL)
        self.engine.currentIndexChanged.connect(self._sync_engine_fields)
        layout.addWidget(self.engine)

        sqlite_box = QGroupBox("SQLite file")
        sqlite_form = QFormLayout(sqlite_box)
        sqlite_row = QHBoxLayout()
        self.sqlite_path = QLineEdit(str(DATABASE_PATH))
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse_sqlite)
        sqlite_row.addWidget(self.sqlite_path, 1)
        sqlite_row.addWidget(browse)
        sqlite_form.addRow("File", sqlite_row)
        layout.addWidget(sqlite_box)
        self._sqlite_box = sqlite_box

        server_box = QGroupBox("Shared server")
        server_form = QFormLayout(server_box)
        self.host = QLineEdit("localhost")
        self.instance = QLineEdit("SQLEXPRESS")
        self.instance.setPlaceholderText("SQLEXPRESS — leave blank for a default instance")
        self.port = QSpinBox()
        self.port.setRange(0, 65535)
        self.port.setSpecialValueText("Default")
        self.port.setValue(0)
        self.database = QLineEdit("PipeAgent")
        self.windows_auth = QCheckBox("Windows authentication (SQL Server)")
        self.windows_auth.toggled.connect(self._sync_auth_fields)
        self.username = QLineEdit()
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.driver = QComboBox()
        self.driver.setEditable(True)
        for name in odbc_driver_names():
            self.driver.addItem(name)
        self.encrypt = QCheckBox("Encrypt connection")
        self.trust_cert = QCheckBox("Trust server certificate")
        self.trust_cert.setChecked(True)
        server_form.addRow("Host", self.host)
        server_form.addRow("Instance", self.instance)
        server_form.addRow("Port", self.port)
        server_form.addRow("Database", self.database)
        server_form.addRow("", self.windows_auth)
        server_form.addRow("User", self.username)
        server_form.addRow("Password", self.password)
        server_form.addRow("ODBC driver", self.driver)
        server_form.addRow("", self.encrypt)
        server_form.addRow("", self.trust_cert)
        layout.addWidget(server_box)
        self._server_box = server_box
        self._mssql_only = [
            widget
            for field in (
                self.instance,
                self.windows_auth,
                self.driver,
                self.encrypt,
                self.trust_cert,
            )
            for widget in (server_form.labelForField(field), field)
            if widget is not None
        ]

        hint = QLabel(
            "Create an empty database on the server first (PipeAgent). "
            "SQL Express is typical on a Windows site PC; PostgreSQL is better "
            "for Linux or a hosted online server. Restart PipeAgent after saving."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#3B5C64;")
        layout.addWidget(hint)

        buttons = QHBoxLayout()
        test_btn = QPushButton("Test connection")
        test_btn.clicked.connect(self._test)
        buttons.addWidget(test_btn)
        buttons.addStretch(1)
        box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        box.accepted.connect(self._save)
        box.rejected.connect(self.reject)
        buttons.addWidget(box)
        layout.addLayout(buttons)

        self._load_existing()
        self._sync_engine_fields()

    def _load_existing(self) -> None:
        profile = load_profile(CONNECTION_PROFILE_PATH)
        if profile is None:
            return
        index = self.engine.findData(profile.engine)
        if index >= 0:
            self.engine.setCurrentIndex(index)
        if profile.sqlite_path:
            self.sqlite_path.setText(profile.sqlite_path)
        self.host.setText(profile.host or "localhost")
        self.instance.setText(profile.instance or "")
        self.port.setValue(int(profile.port) if str(profile.port).isdigit() else 0)
        self.database.setText(profile.database or "PipeAgent")
        self.windows_auth.setChecked(profile.windows_auth)
        self.username.setText(profile.username or "")
        self.password.setText(profile.password or "")
        if profile.driver:
            if self.driver.findText(profile.driver) < 0:
                self.driver.addItem(profile.driver)
            self.driver.setCurrentText(profile.driver)
        self.encrypt.setChecked(profile.encrypt)
        self.trust_cert.setChecked(profile.trust_server_certificate)

    def _sync_engine_fields(self) -> None:
        engine = self.engine.currentData()
        self._sqlite_box.setVisible(engine == ENGINE_SQLITE)
        self._server_box.setVisible(engine != ENGINE_SQLITE)
        mssql = engine == ENGINE_MSSQL
        for widget in self._mssql_only:
            widget.setVisible(mssql)
        if engine == ENGINE_POSTGRESQL and self.port.value() == 0:
            self.port.setValue(5432)
        if engine == ENGINE_MSSQL and self.port.value() == 5432:
            self.port.setValue(0)
        self._sync_auth_fields()
        self.adjustSize()

    def _sync_auth_fields(self) -> None:
        sql_auth = not (
            self.engine.currentData() == ENGINE_MSSQL and self.windows_auth.isChecked()
        )
        self.username.setEnabled(sql_auth)
        self.password.setEnabled(sql_auth)

    def _browse_sqlite(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "SQLite database file",
            self.sqlite_path.text() or str(DATABASE_PATH),
            "SQLite (*.db);;All files (*.*)",
        )
        if path:
            self.sqlite_path.setText(path)

    def _profile(self) -> ConnectionProfile:
        engine = self.engine.currentData() or ENGINE_SQLITE
        port = "" if self.port.value() == 0 else str(self.port.value())
        return profile_from_mapping({
            "engine": engine,
            "sqlite_path": self.sqlite_path.text().strip(),
            "host": self.host.text().strip(),
            "port": port,
            "instance": self.instance.text().strip(),
            "database": self.database.text().strip() or "PipeAgent",
            "username": self.username.text().strip(),
            "password": self.password.text(),
            "windows_auth": self.windows_auth.isChecked(),
            "driver": self.driver.currentText().strip(),
            "encrypt": self.encrypt.isChecked(),
            "trust_server_certificate": self.trust_cert.isChecked(),
        })

    def _test(self) -> None:
        try:
            url = build_url(self._profile(), default_sqlite=DATABASE_PATH)
        except Exception as exc:
            QMessageBox.warning(self, "Database Connection", str(exc))
            return
        ok, message = test_database_url(url)
        if ok:
            QMessageBox.information(self, "Database Connection", message)
        else:
            QMessageBox.warning(self, "Database Connection", message)

    def _save(self) -> None:
        profile = self._profile()
        try:
            url = build_url(profile, default_sqlite=DATABASE_PATH)
            save_profile(CONNECTION_PROFILE_PATH, profile)
        except Exception as exc:
            logger.exception("Could not save database profile")
            QMessageBox.critical(self, "Database Connection", str(exc))
            return
        self._saved = True
        QMessageBox.information(
            self,
            "Database Connection",
            "Connection saved on this workstation.\n\n"
            f"{describe_database_target(url)}\n\n"
            "Restart PipeAgent so every module uses the new server.",
        )
        self.accept()
