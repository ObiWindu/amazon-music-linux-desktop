"""Settings dialog."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
)

from ..services.configuration import (
    REGION_LABELS,
    AppConfig,
)


class SettingsDialog(QDialog):
    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.config = config
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.region_combo = QComboBox()
        for code, label in REGION_LABELS.items():
            self.region_combo.addItem(label, code)
        idx = self.region_combo.findData(config.region)
        if idx >= 0:
            self.region_combo.setCurrentIndex(idx)
        form.addRow("Region", self.region_combo)

        self.homepage_edit = QLineEdit(config.homepage_url)
        form.addRow("Homepage URL", self.homepage_edit)

        self.width_spin = QSpinBox()
        self.width_spin.setRange(640, 4096)
        self.width_spin.setValue(config.window_width)
        self.height_spin = QSpinBox()
        self.height_spin.setRange(480, 4096)
        self.height_spin.setValue(config.window_height)
        form.addRow("Window width", self.width_spin)
        form.addRow("Window height", self.height_spin)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["system", "light", "dark"])
        self.theme_combo.setCurrentText(config.theme)
        form.addRow("Theme", self.theme_combo)

        self.tray_check = QCheckBox("Enable system tray")
        self.tray_check.setChecked(config.tray_enabled)
        form.addRow("", self.tray_check)

        self.min_tray_check = QCheckBox("Minimize to tray")
        self.min_tray_check.setChecked(config.minimize_to_tray)
        form.addRow("", self.min_tray_check)

        self.media_keys_check = QCheckBox("Enable media keys")
        self.media_keys_check.setChecked(config.media_keys_enabled)
        form.addRow("", self.media_keys_check)

        self.dev_diag_check = QCheckBox("Developer diagnostics")
        self.dev_diag_check.setChecked(config.developer_diagnostics)
        form.addRow("", self.dev_diag_check)

        layout.addLayout(form)

        self.note = QLabel("Changes take effect on next launch where noted.")
        self.note.setWordWrap(True)
        layout.addWidget(self.note)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def apply_to(self, config: AppConfig) -> None:
        code = self.region_combo.currentData()
        if code:
            config.region = code
            config.homepage_url = self.homepage_edit.text().strip() or config.homepage_url
        config.window_width = self.width_spin.value()
        config.window_height = self.height_spin.value()
        config.theme = self.theme_combo.currentText()
        config.tray_enabled = self.tray_check.isChecked()
        config.minimize_to_tray = self.min_tray_check.isChecked()
        config.media_keys_enabled = self.media_keys_check.isChecked()
        config.developer_diagnostics = self.dev_diag_check.isChecked()
        config.validate()
