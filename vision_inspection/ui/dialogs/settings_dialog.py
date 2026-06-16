from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from vision_inspection.app.config import AppConfig


class SettingsDialog(QDialog):
    def __init__(self, app_config: AppConfig, project_root: Path, parent=None, camera_controller=None) -> None:
        super().__init__(parent)
        self._app_config = app_config
        self._project_root = project_root
        self._camera_controller = camera_controller
        self.setWindowTitle("系统设置")
        self.resize(620, 520)

        self._build_widgets()
        self._apply_style()
        self._build_layout()
        self._load_config()
        self._bind_events()

    def _build_widgets(self) -> None:
        # --- Camera tab ---
        self.cam_trigger_combo = QComboBox()
        self.cam_trigger_combo.addItems(["Line0", "Software"])
        self.cam_activation_combo = QComboBox()
        self.cam_activation_combo.addItems(["RisingEdge", "FallingEdge", "LevelHigh", "LevelLow"])
        self.cam_debounce_spin = QSpinBox()
        self.cam_debounce_spin.setRange(0, 10000)
        self.cam_debounce_spin.setSuffix(" µs")
        self.cam_exposure_spin = QDoubleSpinBox()
        self.cam_exposure_spin.setRange(20, 1000000)
        self.cam_exposure_spin.setDecimals(1)
        self.cam_exposure_spin.setSuffix(" µs")
        self.cam_gain_spin = QDoubleSpinBox()
        self.cam_gain_spin.setRange(0, 48)
        self.cam_gain_spin.setDecimals(1)
        self.cam_gain_spin.setSuffix(" dB")
        self.cam_gamma_spin = QDoubleSpinBox()
        self.cam_gamma_spin.setRange(0.1, 4.0)
        self.cam_gamma_spin.setDecimals(1)
        self.cam_gamma_spin.setSingleStep(0.1)

        # --- Database tab ---
        self.db_server_edit = QLineEdit()
        self.db_name_edit = QLineEdit()
        self.db_user_edit = QLineEdit()
        self.db_password_edit = QLineEdit()
        self.db_password_edit.setEchoMode(QLineEdit.Password)
        self.db_table_edit = QLineEdit()
        self.db_table_edit.setPlaceholderText("T_SerialNo")
        self.db_result_table_edit = QLineEdit()
        self.db_result_table_edit.setPlaceholderText("T_VisionResult")
        self.db_station_edit = QLineEdit()
        self.db_station_edit.setPlaceholderText("ST001")
        self.db_test_button = QPushButton("测试连接")
        self.db_test_button.setMinimumHeight(36)
        self.db_status_label = QLabel("")
        self.db_status_label.setStyleSheet("color: #64748b; font-size: 12px;")

        # --- Storage tab ---
        self.storage_root_edit = QLineEdit()
        self.storage_log_edit = QLineEdit()
        self.storage_save_pass_check = QCheckBox("保存合格品图片")
        self.storage_save_ng_only_check = QCheckBox("仅保存 NG 图")

        # --- Switch mode tab ---
        self.switch_auto_radio = QRadioButton("自动换型（通过 HTTP API 查询机型）")
        self.switch_manual_radio = QRadioButton("手动换型（操作员手动选择机型）")
        self.api_url_edit = QLineEdit()
        self.api_url_edit.setPlaceholderText("http://192.168.0.101:8080")
        self.api_timeout_spin = QSpinBox()
        self.api_timeout_spin.setRange(100, 10000)
        self.api_timeout_spin.setSuffix(" ms")
        self.api_source_edit = QLineEdit()
        self.api_source_edit.setPlaceholderText("vision-inspection")

        # --- IO tab ---
        self.io_line1_pulse_spin = QSpinBox()
        self.io_line1_pulse_spin.setRange(50, 10000)
        self.io_line1_pulse_spin.setSuffix(" ms")

        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            "QDialog { background: #eef1f5; }"
            "QGroupBox { font-weight: 600; border: 1px solid #dde5ef; border-radius: 10px; margin-top: 10px; background: #ffffff; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: #0f172a; font-size: 13px; font-weight: 700; }"
            "QLabel { color: #111827; }"
            "QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox { min-height: 32px; padding: 0 8px; border: 1px solid #d4dce7; border-radius: 6px; background: #ffffff; }"
            "QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover { border-color: #b8c7d9; }"
            "QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus { border-color: #7c9cc2; }"
            "QPushButton { min-height: 32px; padding: 0 12px; border: 1px solid #d4dce7; border-radius: 6px; background: #f9fbfd; color: #111827; }"
            "QPushButton:hover { background: #f0f5fa; }"
            "QTabWidget::pane { border: 1px solid #dde5ef; border-radius: 10px; background: #ffffff; top: -1px; }"
            "QTabBar::tab { min-width: 100px; min-height: 34px; margin-right: 4px; padding: 0 14px; background: #e8edf4; color: #475569; border-top-left-radius: 8px; border-top-right-radius: 8px; }"
            "QTabBar::tab:selected { background: #ffffff; color: #0f172a; font-weight: 700; }"
            "QRadioButton { spacing: 8px; color: #334155; font-size: 13px; }"
        )

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        tabs = QTabWidget(self)
        tabs.addTab(self._wrap_scroll(self._build_camera_tab()), "相机设置")
        tabs.addTab(self._wrap_scroll(self._build_database_tab()), "数据库")
        tabs.addTab(self._wrap_scroll(self._build_storage_tab()), "存储设置")
        tabs.addTab(self._wrap_scroll(self._build_switch_tab()), "换型模式")
        tabs.addTab(self._wrap_scroll(self._build_io_tab()), "IO 参数")

        root.addWidget(tabs)
        root.addWidget(self.button_box)

    def _wrap_scroll(self, widget: QWidget) -> QScrollArea:
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(widget)
        return scroll

    def _build_camera_tab(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        trigger_group = QGroupBox("触发设置")
        form = QFormLayout(trigger_group)
        form.setContentsMargins(14, 16, 14, 12)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)
        form.addRow("触发源", self.cam_trigger_combo)
        form.addRow("触发沿", self.cam_activation_combo)
        form.addRow("防抖时间", self.cam_debounce_spin)

        param_group = QGroupBox("默认参数（软件启动时恢复）")
        pform = QFormLayout(param_group)
        pform.setContentsMargins(14, 16, 14, 12)
        pform.setHorizontalSpacing(10)
        pform.setVerticalSpacing(8)
        pform.addRow("曝光时间", self.cam_exposure_spin)
        pform.addRow("增益", self.cam_gain_spin)
        pform.addRow("Gamma", self.cam_gamma_spin)

        layout.addWidget(trigger_group)
        layout.addWidget(param_group)
        layout.addStretch(1)
        return page

    def _build_database_tab(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        group = QGroupBox("SQL Server 连接")
        form = QFormLayout(group)
        form.setContentsMargins(14, 16, 14, 12)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)
        form.addRow("服务器地址", self.db_server_edit)
        form.addRow("数据库名", self.db_name_edit)
        form.addRow("用户名", self.db_user_edit)
        form.addRow("密码", self.db_password_edit)
        form.addRow("流水号表名", self.db_table_edit)
        form.addRow("结果表名", self.db_result_table_edit)
        form.addRow("工位 ID", self.db_station_edit)

        button_row = QHBoxLayout()
        button_row.addWidget(self.db_test_button)
        button_row.addWidget(self.db_status_label, 1)
        form.addRow("", button_row)

        layout.addWidget(group)
        layout.addStretch(1)
        return page

    def _build_storage_tab(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        group = QGroupBox("存储路径")
        form = QFormLayout(group)
        form.setContentsMargins(14, 16, 14, 12)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)
        form.addRow("图片根目录", self.storage_root_edit)
        form.addRow("日志根目录", self.storage_log_edit)
        form.addRow("", self.storage_save_pass_check)
        form.addRow("", self.storage_save_ng_only_check)

        layout.addWidget(group)
        layout.addStretch(1)
        return page

    def _build_switch_tab(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        mode_group = QGroupBox("换型模式")
        mode_layout = QVBoxLayout(mode_group)
        mode_layout.setContentsMargins(14, 16, 14, 12)
        mode_layout.setSpacing(10)
        mode_layout.addWidget(self.switch_auto_radio)
        mode_layout.addWidget(self.switch_manual_radio)

        api_group = QGroupBox("HTTP API 配置（自动换型时生效）")
        api_form = QFormLayout(api_group)
        api_form.setContentsMargins(14, 16, 14, 12)
        api_form.setHorizontalSpacing(10)
        api_form.setVerticalSpacing(8)
        api_form.addRow("API 地址", self.api_url_edit)
        api_form.addRow("超时时间", self.api_timeout_spin)
        api_form.addRow("数据源标识", self.api_source_edit)

        layout.addWidget(mode_group)
        layout.addWidget(api_group)
        layout.addStretch(1)
        return page

    def _build_io_tab(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        group = QGroupBox("Line1 输出参数")
        form = QFormLayout(group)
        form.setContentsMargins(14, 16, 14, 12)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)
        form.addRow("合格脉冲宽度", self.io_line1_pulse_spin)

        self.io_test_button = QPushButton("🔌 手动测试 Line1 OK 脉冲（需接好万用表/示波器）")
        self.io_test_button.setMinimumHeight(40)
        self.io_diag_button = QPushButton("🔍 诊断 Line1 输出能力（读取相机支持的输出方式）")
        self.io_diag_button.setMinimumHeight(36)
        self.io_test_status = QLabel("")
        self.io_test_status.setStyleSheet("color: #64748b; font-size: 12px; padding: 2px 0;")
        self.io_test_status.setWordWrap(True)
        self.io_test_status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        test_row = QVBoxLayout()
        test_row.setSpacing(4)
        test_row.addWidget(self.io_test_button)
        test_row.addWidget(self.io_diag_button)
        test_row.addWidget(self.io_test_status)
        form.addRow("", test_row)

        info = QLabel("Line1 输出逻辑：检测合格 → 高电平持续指定脉宽后恢复低电平；不合格 → 保持低电平")
        info.setWordWrap(True)
        info.setStyleSheet("color: #64748b; font-size: 12px; padding: 4px 0;")

        layout.addWidget(group)
        layout.addWidget(info)
        layout.addStretch(1)
        return page

    def _bind_events(self) -> None:
        self.button_box.accepted.connect(self._save_and_accept)
        self.button_box.rejected.connect(self.reject)
        self.db_test_button.clicked.connect(self._test_db_connection)
        self.io_test_button.clicked.connect(self._test_line1_pulse)
        self.io_diag_button.clicked.connect(self._diagnose_line1)

    def _load_config(self) -> None:
        cp = self._app_config.camera_params
        self.cam_exposure_spin.setValue(cp.exposure_us)
        self.cam_gain_spin.setValue(cp.gain_raw)
        self.cam_gamma_spin.setValue(cp.gamma)

        trigger_source_idx = self.cam_trigger_combo.findText(cp.trigger_source)
        if trigger_source_idx >= 0:
            self.cam_trigger_combo.setCurrentIndex(trigger_source_idx)
        trigger_activation_idx = self.cam_activation_combo.findText(cp.trigger_activation)
        if trigger_activation_idx >= 0:
            self.cam_activation_combo.setCurrentIndex(trigger_activation_idx)
        self.cam_debounce_spin.setValue(cp.trigger_debounce_us)

        db = self._app_config.database
        self.db_server_edit.setText(db.server)
        self.db_name_edit.setText(db.database)
        self.db_user_edit.setText(db.username)
        self.db_password_edit.setText(db.password)
        self.db_table_edit.setText(db.serial_table)
        self.db_result_table_edit.setText(db.result_table)
        self.db_station_edit.setText(db.station_id)

        st = self._app_config.storage
        self.storage_root_edit.setText(st.image_root)
        self.storage_log_edit.setText(st.log_root)
        self.storage_save_pass_check.setChecked(st.save_pass_images)

        if self._app_config.switch_mode == "manual":
            self.switch_manual_radio.setChecked(True)
        else:
            self.switch_auto_radio.setChecked(True)

        api = self._app_config.crankshaft_api
        self.api_url_edit.setText(api.base_url)
        self.api_timeout_spin.setValue(api.timeout_ms)
        self.api_source_edit.setText(api.source)

        io = self._app_config.io
        self.io_line1_pulse_spin.setValue(io.line1_pass_duration_ms)

    def _save_and_accept(self) -> None:
        self._app_config.camera_params.exposure_us = self.cam_exposure_spin.value()
        self._app_config.camera_params.gain_raw = self.cam_gain_spin.value()
        self._app_config.camera_params.gamma = self.cam_gamma_spin.value()
        self._app_config.camera_params.trigger_source = self.cam_trigger_combo.currentText()
        self._app_config.camera_params.trigger_activation = self.cam_activation_combo.currentText()
        self._app_config.camera_params.trigger_debounce_us = self.cam_debounce_spin.value()

        self._app_config.database.server = self.db_server_edit.text().strip()
        self._app_config.database.database = self.db_name_edit.text().strip()
        self._app_config.database.username = self.db_user_edit.text().strip()
        self._app_config.database.password = self.db_password_edit.text()
        self._app_config.database.serial_table = self.db_table_edit.text().strip() or "T_SerialNo"
        self._app_config.database.result_table = self.db_result_table_edit.text().strip() or "T_VisionResult"
        self._app_config.database.station_id = self.db_station_edit.text().strip() or "ST001"

        self._app_config.storage.image_root = self.storage_root_edit.text().strip()
        self._app_config.storage.log_root = self.storage_log_edit.text().strip()
        self._app_config.storage.save_pass_images = self.storage_save_pass_check.isChecked()

        self._app_config.switch_mode = "manual" if self.switch_manual_radio.isChecked() else "auto"

        self._app_config.crankshaft_api.base_url = self.api_url_edit.text().strip() or "http://192.168.0.101:8080"
        self._app_config.crankshaft_api.timeout_ms = self.api_timeout_spin.value()
        self._app_config.crankshaft_api.source = self.api_source_edit.text().strip() or "vision-inspection"

        self._app_config.io.line1_pass_duration_ms = self.io_line1_pulse_spin.value()

        self.accept()

    def _test_line1_pulse(self) -> None:
        if self._camera_controller is None:
            self.io_test_status.setText("相机控制器未连接，请从主界面打开设置")
            self.io_test_status.setStyleSheet("color: #ef4444; font-size: 12px; padding: 2px 0;")
            return

        pulse_ms = self.io_line1_pulse_spin.value()
        self.io_test_button.setEnabled(False)
        self.io_test_status.setText(f"正在输出 Line1 OK 脉冲 {pulse_ms} ms ...")
        self.io_test_status.setStyleSheet("color: #f59e0b; font-size: 12px; padding: 2px 0;")

        try:
            self._camera_controller.set_pass_pulse_ms(pulse_ms)
            message = self._camera_controller.emit_pass_output(preferred_device_index=0, channel="Line1")
            self.io_test_status.setText(f"✓ {message} — 请用万用表确认 Line1+/Line1- 之间有 {pulse_ms}ms 高电平脉冲")
            self.io_test_status.setStyleSheet("color: #0f766e; font-size: 12px; font-weight: 600; padding: 2px 0;")
        except Exception as exc:
            self.io_test_status.setText(f"✗ 输出失败: {exc}")
            self.io_test_status.setStyleSheet("color: #ef4444; font-size: 12px; padding: 2px 0;")
        finally:
            self.io_test_button.setEnabled(True)

    def _diagnose_line1(self) -> None:
        if self._camera_controller is None:
            self.io_test_status.setText("相机控制器未连接，请从主界面打开设置")
            self.io_test_status.setStyleSheet("color: #ef4444; font-size: 12px; padding: 2px 0;")
            return

        self.io_diag_button.setEnabled(False)
        self.io_test_status.setText("正在读取 Line1 输出能力 ...")
        self.io_test_status.setStyleSheet("color: #f59e0b; font-size: 12px; padding: 2px 0;")

        try:
            report = self._camera_controller.diagnose_output_line(preferred_device_index=0, channel="Line1")
            self.io_test_status.setText(report)
            self.io_test_status.setStyleSheet(
                "color: #0f172a; font-size: 12px; font-family: monospace; padding: 2px 0;"
            )
        except Exception as exc:
            self.io_test_status.setText(f"✗ 诊断失败: {exc}")
            self.io_test_status.setStyleSheet("color: #ef4444; font-size: 12px; padding: 2px 0;")
        finally:
            self.io_diag_button.setEnabled(True)

    def _test_db_connection(self) -> None:
        server = self.db_server_edit.text().strip()
        database = self.db_name_edit.text().strip()
        username = self.db_user_edit.text().strip()
        password = self.db_password_edit.text()

        if not server or not database:
            self.db_status_label.setText("请填写服务器地址和数据库名")
            self.db_status_label.setStyleSheet("color: #f59e0b; font-size: 12px;")
            return

        try:
            import pyodbc
            conn_str = (
                f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                f"SERVER={server};DATABASE={database};UID={username};PWD={password}"
            )
            conn = pyodbc.connect(conn_str, timeout=5)
            conn.close()
            self.db_status_label.setText("连接成功")
            self.db_status_label.setStyleSheet("color: #0f766e; font-size: 12px; font-weight: 600;")
        except ImportError:
            self.db_status_label.setText("pyodbc 未安装")
            self.db_status_label.setStyleSheet("color: #ef4444; font-size: 12px;")
        except Exception as exc:
            self.db_status_label.setText(f"连接失败: {exc}")
            self.db_status_label.setStyleSheet("color: #ef4444; font-size: 12px;")
