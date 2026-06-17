from __future__ import annotations

from collections import deque
import logging
import os
from pathlib import Path
from time import perf_counter
from typing import Optional

_logger = logging.getLogger("vision_inspection.ui")

from PyQt5.QtCore import QDateTime, QThread, Qt, QTimer
from PyQt5.QtGui import QCloseEvent, QColor, QImage
from PyQt5.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from vision_inspection.app.config import AppConfig, load_app_config, save_app_config
from vision_inspection.application.controllers.camera_controller import CameraController
from vision_inspection.application.controllers.inspection_controller import InspectionController
from vision_inspection.application.controllers.inspection_workflow_controller import InspectionWorkflowController
from vision_inspection.application.controllers.plc_controller import PlcController
from vision_inspection.application.services.crankshaft_api import CrankshaftApiClient, CrankshaftApiError, validate_serial_no
from vision_inspection.application.services.inspection_workflow_service import InspectionExecutionResult, SaveResultSnapshot
from vision_inspection.application.services.report_service import ReportService
from vision_inspection.application.controllers.recipe_controller import RecipeController
from vision_inspection.infrastructure.database import SqlServerClient
from vision_inspection.domain.models.inspection_result import InspectionResult
from vision_inspection.domain.models.recipe import RecipeDocument
from vision_inspection.ui.dialogs.settings_dialog import SettingsDialog
from vision_inspection.ui.history_records_dialog import HistoryRecordsDialog
from vision_inspection.ui.inspection_worker import InspectionWorker
from vision_inspection.ui.plc_listener_worker import PlcListenerWorker
from vision_inspection.ui.recipe_editor_dialog import RecipeEditorDialog
from vision_inspection.ui.widgets.image_canvas import ImageCanvas
from vision_inspection.ui.widgets.roi_result_table import RoiResultTable


class MainWindow(QMainWindow):
    def __init__(
        self,
        recipe_controller: RecipeController,
        camera_controller: CameraController,
        inspection_controller: InspectionController,
        inspection_workflow_controller: InspectionWorkflowController,
        plc_controller: PlcController,
    ) -> None:
        super().__init__()
        self._project_root = Path(__file__).resolve().parents[1]
        self._app_config = load_app_config(self._project_root)
        self._crankshaft_api = CrankshaftApiClient(
            base_url=self._app_config.crankshaft_api.base_url,
            timeout_ms=self._app_config.crankshaft_api.timeout_ms,
            source=self._app_config.crankshaft_api.source,
        )
        self._db_client = SqlServerClient(
            server=self._app_config.database.server,
            database=self._app_config.database.database,
            username=self._app_config.database.username,
            password=self._app_config.database.password,
            serial_table=self._app_config.database.serial_table,
            serial_field=self._app_config.database.serial_field,
            model_field=self._app_config.database.model_field,
            result_table=self._app_config.database.result_table,
            station_id=self._app_config.database.station_id,
        )
        self._report_service = ReportService(self._app_config.storage.image_root)
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._refresh_status_indicators)
        self._status_timer.start(5000)
        self._recipe_controller = recipe_controller
        self._camera_controller = camera_controller
        self._inspection_controller = inspection_controller
        self._inspection_workflow_controller = inspection_workflow_controller
        self._plc_controller = plc_controller
        self._current_recipe: Optional[RecipeDocument] = None
        self._inspection_thread: Optional[QThread] = None
        self._inspection_worker: Optional[InspectionWorker] = None
        self._plc_thread: Optional[QThread] = None
        self._plc_worker: Optional[PlcListenerWorker] = None
        self._external_trigger_listening = False
        self._pending_external_wait = False
        self._external_wait_timeout_count = 0
        self._inspection_started_at: float | None = None
        self._inspection_total_count = 0
        self._inspection_ok_count = 0
        self._inspection_ng_count = 0
        self._consecutive_ng_count = 0
        self._result_history: deque[str] = deque(maxlen=8)

        self.setWindowTitle("视觉检测软件 - 一期骨架")
        self.resize(1280, 800)

        self.recipe_combo = QComboBox()
        self.recipe_combo.setObjectName("RecipeSelector")
        self.refresh_button = QPushButton("刷新配方")
        self.refresh_button.setObjectName("RecipeActionButton")
        self.add_button = QPushButton("新增配方")
        self.add_button.setObjectName("RecipeActionButton")
        self.duplicate_button = QPushButton("复制配方")
        self.duplicate_button.setObjectName("RecipeActionButton")
        self.delete_button = QPushButton("删除配方")
        self.delete_button.setObjectName("RecipeDangerButton")
        self.edit_button = QPushButton("配方编辑")
        self.edit_button.setObjectName("RecipePrimaryButton")
        self.manual_test_button = QPushButton("手动测试")
        self.plc_listen_button = QPushButton("启动 PLC 监听")
        self.plc_stop_button = QPushButton("停止 PLC 监听")
        self.plc_trigger_button = QPushButton("模拟 PLC 触发")

        self.station_label = QLabel("-")
        self.camera_label = QLabel("-")
        self.product_label = QLabel("-")
        self.host_com_label = QLabel("未检测")
        self.plc_label = QLabel("未连接")
        self.recipe_name_label = QLabel("-")
        self.runtime_state_label = QLabel("待机")
        self.header_mode_label = QLabel("待机")
        self.header_cycle_label = QLabel("-")
        self.header_time_label = QLabel("-")
        self.last_error_label = QLabel("-")
        self.last_error_label.setWordWrap(True)
        self.target_cycle_label = QLabel("-")
        self.actual_cycle_label = QLabel("-")
        self.total_count_label = QLabel("0")
        self.ok_count_label = QLabel("0")
        self.ng_count_label = QLabel("0")
        self.yield_label = QLabel("0.0%")
        self.result_label = QLabel("待机")
        self.result_label.setAlignment(Qt.AlignCenter)
        self.current_template_info_label = QLabel("-")
        self.result_duration_label = QLabel("-")
        self.trigger_time_label = QLabel("-")
        self.result_ng_count_label = QLabel("0")
        self.consecutive_ng_label = QLabel("0")
        self.compare_primary_label = QLabel("-")
        self.compare_shadow_label = QLabel("-")
        self.compare_summary_label = QLabel("当前配方未启用并行对照")
        self.compare_summary_label.setWordWrap(True)
        self.recent_save_path_label = QLabel("-")
        self.recent_save_path_label.setWordWrap(True)
        self.log_table = QTableWidget(0, 3)
        self.log_table.setHorizontalHeaderLabels(["时间", "类型", "消息"])
        self.log_table.verticalHeader().setVisible(False)
        self.log_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.log_table.horizontalHeader().setStretchLastSection(True)
        self.log_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.log_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.log_table.setAlternatingRowColors(True)
        self.log_table.setMinimumHeight(170)
        self.footer_state_label = QLabel("系统状态：待机")
        self.footer_version_label = QLabel("版本：v1.0.0")
        self.footer_user_label = QLabel("当前用户：operator")
        self.footer_message_label = QLabel("就绪")
        self.image_fit_button = QPushButton("适应窗口")
        self.image_original_button = QPushButton("原始大小")
        self.image_zoom_in_button = QPushButton("+")
        self.image_zoom_out_button = QPushButton("-")
        self.save_image_button = QPushButton("保存图像")
        self.view_record_button = QPushButton("查看记录")
        self.clear_alarm_button = QPushButton("清除报警")
        self.switch_mode_button = QPushButton("换型: 自动")
        self.switch_serial_input = QLineEdit()
        self.switch_serial_input.setPlaceholderText("输入流水号后按回车查询...")
        self.switch_machine_label = QLabel("-")
        self.switch_machine_combo = QComboBox()
        self.switch_machine_confirm_button = QPushButton("确认切换")
        self.switch_machine_confirm_button.setVisible(False)

        self.nav_run_btn = QPushButton("▶ 运行")
        self.nav_recipe_btn = QPushButton("📋 配方")
        self.nav_setting_btn = QPushButton("⚙ 设置")
        self.nav_run_btn.setCheckable(True)
        self.nav_recipe_btn.setCheckable(True)
        self.nav_setting_btn.setCheckable(True)
        self.nav_run_btn.setChecked(True)
        self._page_stack = QStackedWidget()

        self.camera_param_exposure_spin = self._create_camera_param_spin(20, 1000000, 5000, " μs")
        self.camera_param_gain_spin = self._create_camera_param_spin(0, 24, 0, " dB", 0.1)
        self.camera_param_gamma_spin = self._create_camera_param_spin(0.1, 4.0, 1.0, "", 0.1)
        self.camera_param_framerate_spin = self._create_camera_param_spin(1, 120, 30, " fps")
        self.camera_param_read_button = QPushButton("读取当前值")
        self.camera_param_apply_button = QPushButton("应用")
        self.camera_param_status_label = QLabel("相机未连接")
        self.camera_param_status_label.setStyleSheet("color: #94a3b8; font-size: 11px; padding: 2px;")
        self.db_status_text = QLabel("未检测")
        self.db_status_text.setStyleSheet("color: #64748b; font-size: 12px; font-weight: 600;")
        self.camera_param_widgets: list = [
            self.camera_param_exposure_spin,
            self.camera_param_gain_spin,
            self.camera_param_gamma_spin,
            self.camera_param_framerate_spin,
            self.camera_param_read_button,
            self.camera_param_apply_button,
        ]
        self.history_labels: list[QLabel] = []

        self.image_canvas = ImageCanvas()
        self.roi_table = RoiResultTable()
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._update_clock_display)
        self._clock_timer.start(1000)

        # 定时轮询后台保存结果
        self._save_poll_timer = QTimer(self)
        self._save_poll_timer.timeout.connect(self._poll_save_results)
        self._save_poll_timer.start(500)

        for label in [
            self.result_duration_label,
            self.trigger_time_label,
            self.result_ng_count_label,
            self.current_template_info_label,
            self.product_label,
            self.header_time_label,
            self.compare_primary_label,
            self.compare_shadow_label,
        ]:
            label.setObjectName("DetailValue")

        for label in [
            self.total_count_label,
            self.ok_count_label,
            self.ng_count_label,
            self.yield_label,
            self.consecutive_ng_label,
        ]:
            label.setObjectName("MetricValue")

        self._apply_window_style()
        self._build_ui()
        self._bind_events()
        self._update_clock_display()
        self._set_camera_params_enabled(False)
        self._apply_switch_mode_ui()
        self._camera_controller.set_trigger_activation(self._app_config.camera_params.trigger_activation)
        self._camera_controller.set_pass_pulse_ms(self._app_config.io.line1_pass_duration_ms)
        self._load_recipe_summaries()
        self._refresh_status_indicators()

    def _algorithm_label(self, algorithm: str | None) -> str:
        return RoiResultTable.algorithm_label(algorithm)

    def _apply_window_style(self) -> None:
        self.setStyleSheet(
            "QMainWindow { background: #eef1f5; }"
            "QFrame#TopBar { background: #101722; border-bottom: 1px solid #202a38; }"
            "QFrame#FooterBar { background: #263243; border-top: 1px solid #334155; }"
            "QFrame#SectionCard { background: #ffffff; border: 1px solid #dde5ef; border-radius: 10px; }"
            "QGroupBox { font-weight: 600; border: 1px solid #dde5ef; border-radius: 10px; margin-top: 10px; background: #ffffff; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: #0f172a; font-size: 13px; font-weight: 700; }"
            "QPushButton { min-height: 32px; padding: 0 10px; border: 1px solid #d4dce7; border-radius: 6px; background: #f9fbfd; color: #111827; }"
            "QPushButton:hover { background: #f0f5fa; }"
            "QLabel { color: #111827; }"
            "QLabel#TopCaption { color: #c7d2e0; font-size: 11px; font-weight: 500; }"
            "QLabel#TopValue { color: #ffffff; font-size: 15px; font-weight: 600; }"
            "QLabel#TopAccentValue { color: #7ee081; font-size: 15px; font-weight: 700; }"
            "QLabel#TopTitle { color: #dbe8ff; font-size: 19px; font-weight: 700; }"
            "QLabel#SectionTitle { color: #0f172a; font-size: 16px; font-weight: 700; }"
            "QLabel#DetailCaption { color: #64748b; font-size: 11px; font-weight: 500; }"
            "QLabel#DetailValue { color: #0f172a; font-size: 18px; font-weight: 700; }"
            "QLabel#MetricValue { color: #0f172a; font-size: 22px; font-weight: 800; }"
            "QLabel#PathValue { color: #475569; font-size: 12px; font-weight: 500; }"
            "QLabel#FooterMeta { color: #d5deea; font-size: 12px; font-weight: 500; }"
            "QLabel#FooterAccent { color: #7ee081; font-size: 12px; font-weight: 600; }"
            "QLabel#FooterMessage { color: #f8fafc; font-size: 12px; font-weight: 500; }"
            "QComboBox { min-height: 32px; padding: 0 8px; border: 1px solid #d4dce7; border-radius: 6px; background: #ffffff; }"
            "QComboBox#RecipeSelector { min-height: 36px; padding: 0 36px 0 12px; border: 1px solid #cfd8e3; border-radius: 8px; background: #f8fafc; color: #0f172a; font-size: 13px; font-weight: 600; }"
            "QComboBox#RecipeSelector:hover { background: #f3f7fb; border-color: #b8c7d9; }"
            "QComboBox#RecipeSelector:focus { border-color: #7c9cc2; background: #ffffff; }"
            "QComboBox#RecipeSelector::drop-down { subcontrol-origin: padding; subcontrol-position: top right; width: 28px; border-left: 1px solid #dde5ef; background: #f1f5f9; border-top-right-radius: 8px; border-bottom-right-radius: 8px; }"
            "QComboBox#RecipeSelector QAbstractItemView { border: 1px solid #d7e0ea; background: #ffffff; selection-background-color: #dbeafe; selection-color: #0f172a; outline: 0; padding: 4px; }"
            "QPushButton#RecipeActionButton { min-height: 36px; padding: 0 12px; border: 1px solid #cfd8e3; border-radius: 8px; background: #f8fafc; color: #334155; font-size: 13px; font-weight: 600; }"
            "QPushButton#RecipeActionButton:hover { background: #f3f7fb; border-color: #b8c7d9; color: #0f172a; }"
            "QPushButton#RecipeActionButton:pressed { background: #e8eef5; }"
            "QPushButton#RecipePrimaryButton { min-height: 36px; padding: 0 14px; border: 1px solid #9fb4ca; border-radius: 8px; background: #dfeaf5; color: #0f172a; font-size: 13px; font-weight: 700; }"
            "QPushButton#RecipePrimaryButton:hover { background: #d4e4f2; border-color: #89a4c0; }"
            "QPushButton#RecipePrimaryButton:pressed { background: #c9ddec; }"
            "QPushButton#RecipeDangerButton { min-height: 36px; padding: 0 12px; border: 1px solid #e5b8b8; border-radius: 8px; background: #fff5f5; color: #b42318; font-size: 13px; font-weight: 700; }"
            "QPushButton#RecipeDangerButton:hover { background: #feecec; border-color: #df9898; }"
            "QPushButton#RecipeDangerButton:pressed { background: #fddfdf; }"
            "QTableWidget { border: 1px solid #e2e8f0; border-radius: 8px; gridline-color: #e8edf4; background: #ffffff; alternate-background-color: #f8fafc; font-size: 11px; }"
            "QHeaderView::section { background: #f8fafc; color: #475569; padding: 6px; border: none; border-bottom: 1px solid #e2e8f0; font-size: 11px; font-weight: 700; }"
        )
        self.runtime_state_label.setAlignment(Qt.AlignCenter)
        self.runtime_state_label.setStyleSheet(
            "font-size: 22px; font-weight: 800; color: #1d4ed8; background: #dbeafe; padding: 12px; border-radius: 8px;"
        )
        self.last_error_label.setStyleSheet("color: #64748b; font-size: 12px; padding: 2px 2px 0 2px;")
        self.result_label.setMinimumHeight(116)
        self.result_label.setStyleSheet(
            "font-size: 40px; font-weight: 800; color: #0f172a; background: #e5e7eb;"
            "padding: 18px; border-radius: 8px;"
        )
        self.compare_summary_label.setStyleSheet("color: #475569; font-size: 12px; padding-top: 2px;")
        self.recent_save_path_label.setObjectName("PathValue")
        self.footer_state_label.setObjectName("FooterAccent")
        self.footer_version_label.setObjectName("FooterMeta")
        self.footer_user_label.setObjectName("FooterMeta")
        self.footer_message_label.setObjectName("FooterMessage")

    def _update_clock_display(self) -> None:
        self.header_time_label.setText(QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss"))

    def _poll_save_results(self) -> None:
        """轮询后台保存结果，更新 UI 标签。"""
        try:
            snapshots = self._inspection_workflow_controller.drain_save_results()
        except Exception:
            return
        if not snapshots:
            return
        # 取最新的一个快照
        latest = snapshots[-1]
        if latest.status == "ok":
            self.recent_save_path_label.setText(latest.record_dir)
            self.recent_save_path_label.setStyleSheet("color: #22c55e; font-size: 11px;")
        elif latest.status == "error":
            short_error = latest.error_message[:80]
            self.recent_save_path_label.setText(f"保存失败: {short_error}")
            self.recent_save_path_label.setStyleSheet("color: #ef4444; font-size: 11px; font-weight: bold;")

    def _set_runtime_state_style(self, text: str, foreground: str, background: str) -> None:
        self.runtime_state_label.setText(text)
        self.header_mode_label.setText(text)
        self.footer_state_label.setText(f"系统状态：{text}")
        self.runtime_state_label.setStyleSheet(
            f"font-size: 22px; font-weight: 800; color: {foreground}; background: {background}; padding: 12px; border-radius: 8px;"
        )

    def _create_metric_card(self, title: str, value_label: QLabel, accent: str, helper_text: str) -> QGroupBox:
        group = QGroupBox(title)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(8, 10, 8, 8)
        layout.setSpacing(4)
        value_label.setAlignment(Qt.AlignCenter)
        value_label.setStyleSheet(
            f"font-size: 20px; font-weight: 700; color: {accent}; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px;"
        )
        helper_label = QLabel(helper_text)
        helper_label.setAlignment(Qt.AlignCenter)
        helper_label.setStyleSheet("color: #64748b; font-size: 12px;")
        layout.addWidget(value_label)
        layout.addWidget(helper_label)
        return group

    def _reset_dashboard(self) -> None:
        self._inspection_started_at = None
        self._inspection_total_count = 0
        self._inspection_ok_count = 0
        self._inspection_ng_count = 0
        self._consecutive_ng_count = 0
        self._result_history.clear()
        self.actual_cycle_label.setText("-")
        self.header_cycle_label.setText("-")
        self.total_count_label.setText("0")
        self.ok_count_label.setText("0")
        self.ng_count_label.setText("0")
        self.yield_label.setText("0.0%")
        self.result_duration_label.setText("-")
        self.trigger_time_label.setText("-")
        self.result_ng_count_label.setText("0")
        self.consecutive_ng_label.setText("0")
        self.recent_save_path_label.setText("-")
        self._update_parallel_comparison(None)
        self._refresh_history_bar()

    def _refresh_history_bar(self) -> None:
        history_values = list(self._result_history)
        for index, label in enumerate(self.history_labels):
            if index < len(history_values):
                result_text = history_values[index]
                if result_text == "OK":
                    label.setText("OK")
                    label.setStyleSheet(
                        "font-size: 13px; font-weight: 700; color: #14532d; background: #dcfce7; border-radius: 8px; padding: 8px 0;"
                    )
                elif result_text == "NG":
                    label.setText("NG")
                    label.setStyleSheet(
                        "font-size: 13px; font-weight: 700; color: #991b1b; background: #fee2e2; border-radius: 8px; padding: 8px 0;"
                    )
                else:
                    label.setText("ERR")
                    label.setStyleSheet(
                        "font-size: 13px; font-weight: 700; color: #92400e; background: #fef3c7; border-radius: 8px; padding: 8px 0;"
                    )
            else:
                label.setText("-")
                label.setStyleSheet(
                    "font-size: 13px; font-weight: 700; color: #94a3b8; background: #e2e8f0; border-radius: 8px; padding: 8px 0;"
                )

    def _record_result(self, result_text: str) -> None:
        self._result_history.appendleft(result_text)
        if result_text == "OK":
            self._inspection_ok_count += 1
            self._consecutive_ng_count = 0
        elif result_text == "NG":
            self._inspection_ng_count += 1
            self._consecutive_ng_count += 1
        elif result_text == "ERR":
            self._consecutive_ng_count += 1
        self._inspection_total_count += 1
        self.total_count_label.setText(str(self._inspection_total_count))
        self.ok_count_label.setText(str(self._inspection_ok_count))
        self.ng_count_label.setText(str(self._inspection_ng_count))
        self.consecutive_ng_label.setText(str(self._consecutive_ng_count))
        yield_value = (self._inspection_ok_count / self._inspection_total_count) * 100 if self._inspection_total_count else 0.0
        self.yield_label.setText(f"{yield_value:.1f}%")
        self._refresh_history_bar()

    def _update_cycle_time(self) -> None:
        self._update_cycle_time_from_elapsed(None)

    def _update_cycle_time_from_elapsed(self, elapsed_ms: float | None) -> None:
        if elapsed_ms is not None:
            display_ms = int(elapsed_ms)
            self.actual_cycle_label.setText(f"{display_ms} ms")
            self.header_cycle_label.setText(f"{display_ms} ms")
            self.result_duration_label.setText(f"{display_ms} ms")
            self._inspection_started_at = None
            return
        if self._inspection_started_at is None:
            self.actual_cycle_label.setText("-")
            self.header_cycle_label.setText("-")
            self.result_duration_label.setText("-")
            return
        elapsed_ms = int((perf_counter() - self._inspection_started_at) * 1000)
        self.actual_cycle_label.setText(f"{elapsed_ms} ms")
        self.header_cycle_label.setText(f"{elapsed_ms} ms")
        self.result_duration_label.setText(f"{elapsed_ms} ms")
        self._inspection_started_at = None

    def _append_log(self, level: str, message: str) -> None:
        row = self.log_table.rowCount()
        self.log_table.insertRow(row)
        time_item = QTableWidgetItem(QDateTime.currentDateTime().toString("HH:mm:ss.zzz"))
        level_item = QTableWidgetItem(level)
        message_item = QTableWidgetItem(message)
        if level == "WARN":
            level_item.setForeground(QColor("#f59e0b"))
        elif level == "ERROR":
            level_item.setForeground(QColor("#ef4444"))
        else:
            level_item.setForeground(QColor("#0f766e"))
        self.log_table.setItem(row, 0, time_item)
        self.log_table.setItem(row, 1, level_item)
        self.log_table.setItem(row, 2, message_item)
        self.log_table.scrollToBottom()

    def _push_status_message(self, message: str, level: str = "INFO", log: bool = True) -> None:
        self.statusBar().showMessage(message)
        self.footer_message_label.setText(message)
        if log:
            self._append_log(level, message)

    def _notify_toolbar_action(self, message: str) -> None:
        self._push_status_message(message, log=False)

    def _format_phase_metrics(self, phase_metrics: dict[str, float] | None) -> str:
        if not phase_metrics:
            return ""
        parts = []
        for key, label in [
            ("total_ms", "总"),
            ("capture_ms", "采图"),
            ("inspect_ms", "检测"),
            ("template_load_ms", "模板加载"),
            ("roi_preprocess_ms", "ROI预处理"),
            ("roi_eval_ms", "ROI判定"),
            ("plc_ms", "PLC"),
        ]:
            value = phase_metrics.get(key)
            if value is None:
                continue
            if key == "plc_ms" and value <= 0:
                continue
            parts.append(f"{label} {int(value)} ms")
        return " / ".join(parts)

    def _save_current_image(self) -> None:
        image = self.image_canvas.get_image_array()
        if image is None:
            self._push_status_message("当前没有可保存的图像", level="WARN", log=False)
            return

        default_name = f"inspection_{QDateTime.currentDateTime().toString('yyyyMMdd_HHmmss')}.jpg"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "保存当前图像",
            str((Path.cwd() / default_name)),
            "JPEG 图像 (*.jpg *.jpeg);;PNG 图像 (*.png)",
        )
        if not file_path:
            return

        image_path = Path(file_path)
        try:
            qimage = self._numpy_to_qimage_for_save(image)
            if not qimage.save(str(image_path)):
                raise RuntimeError("QImage 保存失败")
            self._push_status_message(f"图像已保存: {image_path}", log=False)
        except Exception as exc:
            QMessageBox.critical(self, "保存图像失败", str(exc))
            self._push_status_message(f"保存图像失败: {exc}", level="ERROR")

    def _resolve_record_root(self) -> Path | None:
        candidate_path = self.recent_save_path_label.text().strip()
        if candidate_path and candidate_path != "-":
            resolved = Path(candidate_path)
            if not resolved.is_absolute():
                resolved = Path(self._app_config.storage.image_root) / resolved
            if resolved.exists():
                return resolved if resolved.is_dir() else resolved.parent

        if self._current_recipe is None:
            return None

        root_dir = Path(self._current_recipe.recipe.storage.root_dir or self._app_config.storage.image_root)
        if not root_dir.is_absolute():
            root_dir = Path(self._app_config.storage.image_root) / root_dir
        record_root = root_dir / "records"
        if self._current_recipe.recipe.storage.recipe_subdir_mode == "by_recipe":
            record_root = record_root / self._current_recipe.recipe.id
        return record_root

    def _open_record_history(self) -> None:
        record_root = self._resolve_record_root()
        if record_root is None or not record_root.exists():
            self._push_status_message("当前没有可查看的历史记录", level="WARN", log=False)
            return

        dialog = HistoryRecordsDialog(record_root=record_root, parent=self)
        dialog.exec_()

    def _create_camera_param_spin(self, min_val: float, max_val: float, default: float, suffix: str = "", step: float = 1) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(min_val, max_val)
        spin.setValue(default)
        spin.setDecimals(1 if step < 1 else 0)
        spin.setSingleStep(step)
        if suffix:
            spin.setSuffix(suffix)
        spin.setMinimumHeight(32)
        spin.setStyleSheet(
            "QDoubleSpinBox { min-height: 32px; padding: 0 8px; border: 1px solid #d4dce7; border-radius: 6px; background: #ffffff; color: #0f172a; font-size: 13px; font-weight: 600; }"
            "QDoubleSpinBox:hover { border-color: #b8c7d9; }"
            "QDoubleSpinBox:focus { border-color: #7c9cc2; }"
            "QDoubleSpinBox:disabled { background: #e8edf4; color: #94a3b8; }"
        )
        return spin

    def _numpy_to_qimage_for_save(self, image):
        if image.ndim == 2:
            return QImage(image.data, image.shape[1], image.shape[0], image.strides[0], QImage.Format_Grayscale8).copy()
        rgb_image = image[:, :, ::-1].copy()
        return QImage(rgb_image.data, rgb_image.shape[1], rgb_image.shape[0], rgb_image.strides[0], QImage.Format_RGB888).copy()

    def _clear_alarm_state(self) -> None:
        self.last_error_label.setText("-")
        if self._current_recipe is not None:
            self._set_runtime_state_style("待机", "#1d4ed8", "#dbeafe")
        self._push_status_message("报警状态已清除")

    def _read_camera_params(self) -> None:
        try:
            params = self._camera_controller.get_camera_params(preferred_device_index=0)
        except Exception as exc:
            self._push_status_message(f"读取相机参数失败: {exc}", level="ERROR")
            self.camera_param_status_label.setText("读取失败")
            self.camera_param_status_label.setStyleSheet("color: #ef4444; font-size: 11px; padding: 2px;")
            return

        if not params:
            self.camera_param_status_label.setText("相机不支持参数读取")
            self.camera_param_status_label.setStyleSheet("color: #f59e0b; font-size: 11px; padding: 2px;")
            return

        if "exposure_us" in params:
            self.camera_param_exposure_spin.setValue(params["exposure_us"])
        if "gain_raw" in params:
            self.camera_param_gain_spin.setValue(params["gain_raw"])
        if "gamma" in params:
            self.camera_param_gamma_spin.setValue(params["gamma"])
        if "frame_rate" in params:
            self.camera_param_framerate_spin.setValue(params["frame_rate"])

        self.camera_param_status_label.setText("已读取当前值")
        self.camera_param_status_label.setStyleSheet("color: #0f766e; font-size: 11px; padding: 2px;")
        self._push_status_message("相机参数已读取")

    def _apply_camera_params(self) -> None:
        param_map = {
            "ExposureTime": self.camera_param_exposure_spin.value(),
            "GainRaw": self.camera_param_gain_spin.value(),
            "Gamma": self.camera_param_gamma_spin.value(),
            "AcquisitionFrameRate": self.camera_param_framerate_spin.value(),
        }

        applied_count = 0
        failed_nodes: list[str] = []
        skipped_nodes: list[str] = []
        for node_name, value in param_map.items():
            try:
                self._camera_controller.set_camera_param(node_name, value, preferred_device_index=0)
                applied_count += 1
            except Exception as exc:
                err_msg = str(exc)
                if "0x80000100" in err_msg or "0x80000001" in err_msg:
                    skipped_nodes.append(node_name)
                else:
                    failed_nodes.append(f"{node_name}={value}")

        if skipped_nodes:
            self.camera_param_status_label.setText(f"已应用 {applied_count} 项（{len(skipped_nodes)} 项不支持）")
            self.camera_param_status_label.setStyleSheet("color: #0f766e; font-size: 11px; padding: 2px;")
        if failed_nodes:
            self.camera_param_status_label.setText(f"部分失败: {'; '.join(failed_nodes)}")
            self.camera_param_status_label.setStyleSheet("color: #f59e0b; font-size: 11px; padding: 2px;")
            self._push_status_message(f"相机参数应用完成: {applied_count} 成功, {len(failed_nodes)} 失败, {len(skipped_nodes)} 跳过", level="WARN")
        else:
            self.camera_param_status_label.setText("参数已应用")
            self.camera_param_status_label.setStyleSheet("color: #0f766e; font-size: 11px; padding: 2px;")
            self._push_status_message(f"相机参数已应用: {applied_count} 项")
        if applied_count > 0:
            self._save_camera_params_to_config()

    def _apply_saved_camera_params(self) -> None:
        cp = self._app_config.camera_params
        saved_params = {
            "ExposureTime": cp.exposure_us,
            "GainRaw": cp.gain_raw,
            "Gamma": cp.gamma,
            "AcquisitionFrameRate": cp.frame_rate,
        }
        applied = 0
        skipped = 0
        for node_name, value in saved_params.items():
            try:
                self._camera_controller.set_camera_param(node_name, value, preferred_device_index=0)
                applied += 1
            except Exception as exc:
                err_msg = str(exc)
                if "0x80000100" in err_msg or "0x80000001" in err_msg:
                    skipped += 1
                pass
        if applied > 0:
            self.camera_param_exposure_spin.setValue(cp.exposure_us)
            self.camera_param_gain_spin.setValue(cp.gain_raw)
            self.camera_param_gamma_spin.setValue(cp.gamma)
            self.camera_param_framerate_spin.setValue(cp.frame_rate)
            self.camera_param_status_label.setText(f"已恢复 {applied} 项参数" + (f"（{skipped} 项不支持）" if skipped else ""))
            self.camera_param_status_label.setStyleSheet("color: #0f766e; font-size: 11px; padding: 2px;")

    def _save_camera_params_to_config(self) -> None:
        self._app_config.camera_params.exposure_us = self.camera_param_exposure_spin.value()
        self._app_config.camera_params.gain_raw = self.camera_param_gain_spin.value()
        self._app_config.camera_params.gamma = self.camera_param_gamma_spin.value()
        self._app_config.camera_params.frame_rate = self.camera_param_framerate_spin.value()
        save_app_config(self._app_config, self._project_root)

    def _create_top_status_item(self, title: str, value_label: QLabel, accent: bool = False) -> QWidget:
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(2)
        caption = QLabel(title)
        caption.setObjectName("TopCaption")
        value_label.setObjectName("TopAccentValue" if accent else "TopValue")
        layout.addWidget(caption)
        layout.addWidget(value_label)
        return container

    def _refresh_status_indicators(self) -> None:
        try:
            devices = self._camera_controller.list_devices()
            if devices:
                ip = devices[0].ip_address or devices[0].display_name
                self.camera_label.setText(f"{ip} 已连接")
                self.camera_label.setStyleSheet("color: #55b56a; font-size: 14px; font-weight: 600;")
            else:
                self.camera_label.setText("未连接")
                self.camera_label.setStyleSheet("color: #94a3b8; font-size: 14px; font-weight: 600;")
        except Exception:
            self.camera_label.setText("未连接")
            self.camera_label.setStyleSheet("color: #94a3b8; font-size: 14px; font-weight: 600;")

        try:
            status = self._crankshaft_api.check_health()
            if status == "ok":
                self.host_com_label.setText("已连接")
                self.host_com_label.setStyleSheet("color: #55b56a; font-size: 14px; font-weight: 600;")
            elif status == "no_service":
                self.host_com_label.setText("服务未启动")
                self.host_com_label.setStyleSheet("color: #f59e0b; font-size: 14px; font-weight: 600;")
            else:
                self.host_com_label.setText("网络断开")
                self.host_com_label.setStyleSheet("color: #ef4444; font-size: 14px; font-weight: 600;")
        except Exception:
            self.host_com_label.setText("未检测")
            self.host_com_label.setStyleSheet("color: #94a3b8; font-size: 14px; font-weight: 600;")

    def _open_settings_dialog(self) -> None:
        dialog = SettingsDialog(self._app_config, self._project_root, self, camera_controller=self._camera_controller)
        if dialog.exec_() == QDialog.Accepted:
            save_app_config(self._app_config, self._project_root)
            self._crankshaft_api = CrankshaftApiClient(
                base_url=self._app_config.crankshaft_api.base_url,
                timeout_ms=self._app_config.crankshaft_api.timeout_ms,
                source=self._app_config.crankshaft_api.source,
            )
            self._camera_controller.set_trigger_activation(self._app_config.camera_params.trigger_activation)
            self._camera_controller.set_pass_pulse_ms(self._app_config.io.line1_pass_duration_ms)
            self._apply_switch_mode_ui()
            self._push_status_message("设置已保存")

    def _open_report_export(self) -> None:
        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出报表", str(Path.cwd() / "检测报表.xlsx"), "Excel 文件 (*.xlsx)"
        )
        if not file_path:
            return
        try:
            output = self._report_service.export_excel(file_path)
            self._push_status_message(f"报表已导出: {output}")
            QMessageBox.information(self, "导出成功", f"报表已保存到:\n{output}")
        except Exception as exc:
            QMessageBox.critical(self, "导出失败", str(exc))
            self._push_status_message(f"报表导出失败: {exc}", level="ERROR")

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "关于",
            "百力通通机视觉检测软件 v1.6\n\n"
            "公司：百力通（重庆）发动机有限公司\n"
            "技术栈：PyQt5 + OpenCV + 海康 MVS SDK\n"
            "检测引擎：二值化 + YOLOv8 AI",
        )

    def _apply_switch_mode_ui(self) -> None:
        is_manual = self._app_config.switch_mode == "manual"
        self.switch_serial_input.setVisible(not is_manual)
        self.switch_machine_label.setVisible(not is_manual)
        self.switch_machine_combo.setVisible(is_manual)
        self.switch_machine_confirm_button.setVisible(is_manual)
        if is_manual:
            self.switch_mode_button.setText("换型: 手动")
            self.switch_machine_combo.clear()
            for summary in self._recipe_controller.list_recipe_summaries():
                self.switch_machine_combo.addItem(summary.name, summary.recipe_id)
        else:
            self.switch_mode_button.setText("换型: 自动")

    def _on_switch_mode_toggle(self) -> None:
        from vision_inspection.app.config import save_app_config
        if self._app_config.switch_mode == "auto":
            self._app_config.switch_mode = "manual"
        else:
            self._app_config.switch_mode = "auto"
        save_app_config(self._app_config, self._project_root)
        self._apply_switch_mode_ui()
        self._push_status_message(f"换型模式已切换为: {'手动换型' if self._app_config.switch_mode == 'manual' else '自动换型'}")

    def _on_manual_switch_confirm(self) -> None:
        recipe_id = self.switch_machine_combo.currentData()
        if recipe_id is None:
            self._push_status_message("请先选择机型", level="WARN")
            return
        reply = QMessageBox.question(
            self, "确认切换",
            f"确认切换至机型：{self.switch_machine_combo.currentText()}？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self._show_recipe(self._recipe_controller.get_recipe(recipe_id))
        self._push_status_message(f"已手动切换至: {self.switch_machine_combo.currentText()}")

    def _match_recipe_for_model(self, full_model: str, summaries: list) -> object | None:
        """根据机型号匹配配方，按优先级：recipe_id 精确匹配 > name 精确匹配 > product_name 精确匹配 > 前缀匹配。"""
        model = full_model.strip()
        # 1) recipe_id 精确匹配
        matched = next((s for s in summaries if s.recipe_id == model), None)
        if matched is not None:
            return matched
        # 2) name 精确匹配
        matched = next((s for s in summaries if s.name == model), None)
        if matched is not None:
            return matched
        # 3) product_name 精确匹配
        matched = next((s for s in summaries if s.product_name == model), None)
        if matched is not None:
            return matched
        # 4) 前缀匹配（model 是 name 或 product_name 的前缀）
        matched = next((s for s in summaries if s.name.startswith(model) or s.product_name.startswith(model)), None)
        if matched is not None:
            return matched
        # 5) name 或 product_name 是 model 的前缀（例如 model="19V3_XXX", name="19V3"）
        matched = next((s for s in summaries if model.startswith(s.name) or (s.product_name and model.startswith(s.product_name))), None)
        return matched

    def _on_serial_input_return(self) -> None:
        serial_no = self.switch_serial_input.text().strip()
        if not serial_no:
            self._push_status_message("请输入流水号", level="WARN")
            return
        self._try_auto_switch(serial_no)

    def _try_auto_switch(self, serial_no: str) -> bool:
        error = validate_serial_no(serial_no)
        if error:
            self._push_status_message(error, level="WARN")
            self.switch_machine_label.setText("流水号无效")
            return False

        try:
            full_model = self._crankshaft_api.get_machine_type(serial_no)
        except CrankshaftApiError as exc:
            self._push_status_message(f"查询机型失败: {exc}", level="ERROR")
            self.switch_machine_label.setText("查询失败")
            return False

        self.switch_machine_label.setText(full_model)

        summaries = self._recipe_controller.list_recipe_summaries()
        matched = self._match_recipe_for_model(full_model, summaries)
        if matched is None:
            self._push_status_message(
                f"未找到配方: 机型 '{full_model}'，请新建对应配方文件",
                level="WARN",
            )
            return False

        current_id = self._current_recipe.recipe.id if self._current_recipe else None
        if matched.recipe_id == current_id:
            self._push_status_message(f"配方未变化: {matched.recipe_id} ({full_model})")
            return True

        self._show_recipe(self._recipe_controller.get_recipe(matched.recipe_id))
        self._push_status_message(f"自动换型: {current_id or '无'} → {matched.recipe_id} ({full_model})")
        return True

    def _build_top_bar(self) -> QWidget:
        panel = QFrame(self)
        panel.setObjectName("TopBar")
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(4)

        title_label = QLabel("视觉检测系统")
        title_label.setObjectName("TopTitle")
        layout.addWidget(title_label)
        layout.addSpacing(12)
        layout.addWidget(self._create_top_status_item("工位", self.station_label))
        layout.addWidget(self._create_top_status_item("相机", self.camera_label, accent=True))
        layout.addWidget(self._create_top_status_item("PLC", self.plc_label, accent=True))
        layout.addWidget(self._create_top_status_item("配方", self.recipe_name_label))
        layout.addWidget(self._create_top_status_item("上位机", self.host_com_label, accent=True))
        layout.addWidget(self._create_top_status_item("模式", self.header_mode_label, accent=True))
        layout.addWidget(self._create_top_status_item("节拍", self.header_cycle_label, accent=True))
        layout.addStretch(1)
        self.header_time_label.setStyleSheet("color: #f8fafc; font-size: 15px; font-weight: 600;")
        layout.addWidget(self.header_time_label)
        return panel

    def _build_nav_bar(self) -> QWidget:
        bar = QFrame(self)
        bar.setObjectName("NavBar")
        bar.setStyleSheet(
            "QFrame#NavBar { background: #ffffff; border-bottom: 2px solid #e2e8f0; }"
        )
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(4)

        nav_style = (
            "QPushButton { min-height: 40px; padding: 0 20px; border: none; border-bottom: 3px solid transparent;"
            "background: transparent; color: #64748b; font-size: 14px; font-weight: 600; }"
            "QPushButton:hover { color: #0f172a; background: #f1f5f9; }"
            "QPushButton:checked { color: #1d4ed8; border-bottom: 3px solid #1d4ed8; background: #eff6ff; }"
        )
        for btn in [self.nav_run_btn, self.nav_recipe_btn, self.nav_setting_btn]:
            btn.setStyleSheet(nav_style)

        nav_group = QButtonGroup(self)
        nav_group.addButton(self.nav_run_btn, 0)
        nav_group.addButton(self.nav_recipe_btn, 1)
        nav_group.addButton(self.nav_setting_btn, 2)
        nav_group.buttonClicked[int].connect(self._page_stack.setCurrentIndex)

        layout.addWidget(self.nav_run_btn)
        layout.addWidget(self.nav_recipe_btn)
        layout.addWidget(self.nav_setting_btn)
        layout.addStretch(1)
        return bar

    def _build_run_page(self) -> QWidget:
        page = QWidget(self)
        layout = QHBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_run_right_panel())
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 3)
        layout.addWidget(splitter)
        return page

    def _build_run_right_panel(self) -> QWidget:
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        result_group = QGroupBox("检测结果")
        result_layout = QHBoxLayout(result_group)
        result_layout.setContentsMargins(10, 14, 10, 10)
        result_layout.setSpacing(10)
        result_layout.addWidget(self.result_label, 2)
        detail_grid = QGridLayout()
        detail_grid.setHorizontalSpacing(8)
        detail_grid.setVerticalSpacing(8)
        detail_grid.addWidget(self._build_result_detail_cell("耗时", self.result_duration_label), 0, 0)
        detail_grid.addWidget(self._build_result_detail_cell("触发时间", self.trigger_time_label), 0, 1)
        detail_grid.addWidget(self._build_result_detail_cell("NG 数量", self.result_ng_count_label), 1, 0)
        detail_grid.addWidget(self._build_result_detail_cell("连续 NG", self.consecutive_ng_label), 1, 1)
        result_layout.addLayout(detail_grid, 3)

        roi_group = QGroupBox("ROI 检测结果")
        roi_layout = QVBoxLayout(roi_group)
        roi_layout.setContentsMargins(8, 14, 8, 8)
        roi_layout.addWidget(self.roi_table)

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(10)
        bottom_row.addWidget(self._build_stats_panel(), 3)

        action_group = QGroupBox("操作")
        action_layout = QVBoxLayout(action_group)
        action_layout.setContentsMargins(10, 14, 10, 10)
        action_layout.setSpacing(8)
        action_layout.addWidget(self.manual_test_button)
        action_layout.addWidget(self.save_image_button)
        action_layout.addWidget(self.view_record_button)
        action_layout.addWidget(self.clear_alarm_button)
        action_layout.addStretch(1)
        bottom_row.addWidget(action_group, 2)

        layout.addWidget(result_group)
        layout.addWidget(roi_group, 2)
        layout.addLayout(bottom_row)
        return panel

    def _build_recipe_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        control_group = QGroupBox("配方控制")
        control_layout = QVBoxLayout(control_group)
        control_layout.setContentsMargins(14, 18, 14, 14)
        control_layout.setSpacing(10)

        recipe_row = QHBoxLayout()
        recipe_row.setSpacing(8)
        recipe_row.addWidget(QLabel("当前配方："))
        recipe_row.addWidget(self.recipe_combo, 1)
        recipe_row.addWidget(self.refresh_button)
        recipe_row.addWidget(self.edit_button)
        control_layout.addLayout(recipe_row)

        info_row = QHBoxLayout()
        info_row.setSpacing(16)
        info_row.addWidget(QLabel("当前模板："))
        info_row.addWidget(self.current_template_info_label, 1)
        info_row.addWidget(QLabel("当前产品："))
        info_row.addWidget(self.product_label, 1)
        control_layout.addLayout(info_row)

        edit_row = QHBoxLayout()
        edit_row.setSpacing(8)
        edit_row.addWidget(self.add_button)
        edit_row.addWidget(self.duplicate_button)
        edit_row.addWidget(self.delete_button)
        edit_row.addStretch(1)
        control_layout.addLayout(edit_row)

        switch_group = QGroupBox("换型模式")
        switch_layout = QVBoxLayout(switch_group)
        switch_layout.setContentsMargins(14, 18, 14, 14)
        switch_layout.setSpacing(8)
        switch_row = QHBoxLayout()
        switch_row.setSpacing(8)
        switch_row.addWidget(self.switch_mode_button)
        self.switch_machine_combo.setMinimumWidth(160)
        switch_row.addWidget(self.switch_machine_combo, 1)
        switch_row.addWidget(self.switch_machine_confirm_button)
        switch_row.addWidget(self.switch_serial_input, 1)
        switch_row.addWidget(self.switch_machine_label)
        switch_layout.addLayout(switch_row)

        plc_group = QGroupBox("IO 监听")
        plc_layout = QHBoxLayout(plc_group)
        plc_layout.setContentsMargins(14, 18, 14, 14)
        plc_layout.setSpacing(8)
        plc_layout.addWidget(self.plc_listen_button)
        plc_layout.addWidget(self.plc_stop_button)
        plc_layout.addWidget(self.plc_trigger_button)
        plc_layout.addStretch(1)

        comparison = self._build_comparison_panel()

        layout.addWidget(control_group)
        layout.addWidget(switch_group)
        layout.addWidget(plc_group)
        layout.addWidget(comparison)
        layout.addStretch(1)
        return page

    def _build_setting_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        top_row = QHBoxLayout()
        top_row.setSpacing(12)
        top_row.addWidget(self._build_camera_params_panel(), 3)

        misc_group = QGroupBox("系统配置")
        misc_layout = QVBoxLayout(misc_group)
        misc_layout.setContentsMargins(14, 18, 14, 14)
        misc_layout.setSpacing(10)

        db_status_row = QHBoxLayout()
        db_status_row.addWidget(QLabel("数据库状态："))
        self.db_status_text = QLabel("未检测")
        self.db_status_text.setStyleSheet("color: #64748b; font-size: 12px; font-weight: 600;")
        db_status_row.addWidget(self.db_status_text, 1)

        settings_btn = QPushButton("打开系统设置...")
        settings_btn.setObjectName("RecipeActionButton")
        settings_btn.setMinimumHeight(36)
        settings_btn.clicked.connect(self._open_settings_dialog)

        report_btn = QPushButton("导出检测报表...")
        report_btn.setObjectName("RecipeActionButton")
        report_btn.setMinimumHeight(36)
        report_btn.clicked.connect(self._open_report_export)

        about_btn = QPushButton("关于本软件")
        about_btn.setObjectName("RecipeActionButton")
        about_btn.setMinimumHeight(36)
        about_btn.clicked.connect(self._show_about)

        version_label = QLabel("版本：v1.6 — 百力通（重庆）发动机有限公司")
        version_label.setStyleSheet("color: #94a3b8; font-size: 12px; padding: 4px 0;")

        misc_layout.addLayout(db_status_row)
        misc_layout.addWidget(settings_btn)
        misc_layout.addWidget(report_btn)
        misc_layout.addWidget(about_btn)
        misc_layout.addStretch(1)
        misc_layout.addWidget(version_label)
        top_row.addWidget(misc_group, 2)

        layout.addLayout(top_row)
        layout.addStretch(1)
        return page

    def _build_ui(self) -> None:
        central = QWidget(self)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_top_bar())
        root_layout.addWidget(self._build_nav_bar())

        self._page_stack.addWidget(self._build_run_page())
        self._page_stack.addWidget(self._build_recipe_page())
        self._page_stack.addWidget(self._build_setting_page())
        root_layout.addWidget(self._page_stack, 1)
        root_layout.addWidget(self._build_footer_bar())

        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar(self))
        self.statusBar().hide()
        self._push_status_message("界面已加载，等待后续接入相机、检测和 PLC")

    def _build_left_panel(self) -> QWidget:
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(self._build_image_panel(), 4)
        layout.addWidget(self._build_log_panel(), 2)
        return panel

    def _build_image_panel(self) -> QWidget:
        panel = QFrame(self)
        panel.setObjectName("SectionCard")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        header_row = QHBoxLayout()
        dot_label = QLabel("●")
        dot_label.setStyleSheet("color: #55b56a; font-size: 12px;")
        title_label = QLabel("最新结果")
        title_label.setObjectName("SectionTitle")
        header_row.addWidget(dot_label)
        header_row.addWidget(title_label)
        header_row.addStretch(1)
        for button in [self.image_fit_button, self.image_original_button, self.image_zoom_in_button, self.image_zoom_out_button]:
            header_row.addWidget(button)
        layout.addLayout(header_row)
        layout.addWidget(self.image_canvas, 1)
        return panel

    def _build_log_panel(self) -> QWidget:
        panel = QFrame(self)
        panel.setObjectName("SectionCard")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        title_label = QLabel("系统日志")
        title_label.setObjectName("SectionTitle")
        layout.addWidget(title_label)
        layout.addWidget(self.log_table)
        return panel

    def _build_result_detail_cell(self, title: str, value_label: QLabel) -> QWidget:
        cell = QFrame(self)
        cell.setObjectName("SectionCard")
        layout = QVBoxLayout(cell)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)
        title_label = QLabel(title)
        title_label.setObjectName("DetailCaption")
        value_label.setObjectName("DetailValue")
        layout.addWidget(title_label)
        layout.addWidget(value_label)
        return cell

    def _build_stats_panel(self) -> QWidget:
        group = QGroupBox("统计信息（今日）")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(10, 14, 10, 10)
        layout.setSpacing(8)

        metrics_row = QGridLayout()
        metrics_row.setHorizontalSpacing(8)
        metrics_row.setVerticalSpacing(8)
        metrics_row.addWidget(self._build_result_detail_cell("OK 数", self.ok_count_label), 0, 0)
        metrics_row.addWidget(self._build_result_detail_cell("NG 数", self.ng_count_label), 0, 1)
        metrics_row.addWidget(self._build_result_detail_cell("OK 率", self.yield_label), 0, 2)
        metrics_row.addWidget(self._build_result_detail_cell("连续 NG", self.consecutive_ng_label), 1, 0, 1, 3)

        recent_group = QFrame(self)
        recent_group.setObjectName("SectionCard")
        recent_layout = QVBoxLayout(recent_group)
        recent_layout.setContentsMargins(10, 8, 10, 8)
        recent_layout.setSpacing(4)
        recent_title = QLabel("最近保存")
        recent_title.setObjectName("DetailCaption")
        recent_layout.addWidget(recent_title)
        recent_layout.addWidget(self.recent_save_path_label)

        layout.addLayout(metrics_row)
        layout.addWidget(recent_group)
        return group

    def _build_comparison_panel(self) -> QWidget:
        group = QGroupBox("并行对照")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(10, 14, 10, 10)
        layout.setSpacing(8)

        comparison_grid = QGridLayout()
        comparison_grid.setHorizontalSpacing(8)
        comparison_grid.setVerticalSpacing(8)
        comparison_grid.addWidget(self._build_result_detail_cell("主判定", self.compare_primary_label), 0, 0)
        comparison_grid.addWidget(self._build_result_detail_cell("并行算法", self.compare_shadow_label), 0, 1)

        summary_card = QFrame(self)
        summary_card.setObjectName("SectionCard")
        summary_layout = QVBoxLayout(summary_card)
        summary_layout.setContentsMargins(10, 8, 10, 8)
        summary_layout.setSpacing(4)
        summary_title = QLabel("对照摘要")
        summary_title.setObjectName("DetailCaption")
        summary_layout.addWidget(summary_title)
        summary_layout.addWidget(self.compare_summary_label)

        layout.addLayout(comparison_grid)
        layout.addWidget(summary_card)
        return group

    def _build_camera_params_panel(self) -> QWidget:
        group = QGroupBox("相机参数")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(10, 14, 10, 10)
        layout.setSpacing(8)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(6)

        exposure_label = QLabel("曝光时间")
        exposure_label.setStyleSheet("color: #334155; font-size: 12px; font-weight: 600;")
        gain_label = QLabel("增益")
        gain_label.setStyleSheet("color: #334155; font-size: 12px; font-weight: 600;")
        gamma_label = QLabel("Gamma")
        gamma_label.setStyleSheet("color: #334155; font-size: 12px; font-weight: 600;")
        framerate_label = QLabel("帧率")
        framerate_label.setStyleSheet("color: #334155; font-size: 12px; font-weight: 600;")

        form.addRow(exposure_label, self.camera_param_exposure_spin)
        form.addRow(gain_label, self.camera_param_gain_spin)
        form.addRow(gamma_label, self.camera_param_gamma_spin)
        form.addRow(framerate_label, self.camera_param_framerate_spin)

        button_row = QHBoxLayout()
        button_row.setSpacing(8)
        self.camera_param_read_button.setObjectName("RecipeActionButton")
        self.camera_param_apply_button.setObjectName("RecipePrimaryButton")
        self.camera_param_read_button.setMinimumHeight(32)
        self.camera_param_apply_button.setMinimumHeight(32)
        button_row.addWidget(self.camera_param_read_button)
        button_row.addWidget(self.camera_param_apply_button)

        layout.addLayout(form)
        layout.addWidget(self.camera_param_status_label)
        layout.addLayout(button_row)
        return group

    def _build_right_panel(self) -> QWidget:
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        control_group = QGroupBox("配方控制")
        control_layout = QVBoxLayout(control_group)
        control_layout.setContentsMargins(10, 14, 10, 10)
        control_layout.setSpacing(8)
        recipe_row = QHBoxLayout()
        recipe_row.setSpacing(6)
        recipe_row.addWidget(self.recipe_combo, 1)
        recipe_row.addWidget(self.refresh_button)
        recipe_row.addWidget(self.edit_button)
        edit_row = QHBoxLayout()
        edit_row.setSpacing(6)
        edit_row.addWidget(self.add_button)
        edit_row.addWidget(self.duplicate_button)
        edit_row.addWidget(self.delete_button)
        plc_row = QHBoxLayout()
        plc_row.setSpacing(6)
        plc_row.addWidget(self.plc_listen_button)
        plc_row.addWidget(self.plc_stop_button)
        plc_row.addWidget(self.plc_trigger_button)
        template_row = QHBoxLayout()
        template_row.addWidget(QLabel("当前模板："))
        template_row.addWidget(self.current_template_info_label, 1)
        product_row = QHBoxLayout()
        product_row.addWidget(QLabel("当前产品："))
        product_row.addWidget(self.product_label, 1)
        control_layout.addLayout(recipe_row)
        control_layout.addLayout(template_row)
        control_layout.addLayout(product_row)
        control_layout.addLayout(edit_row)
        control_layout.addLayout(plc_row)

        switch_row = QHBoxLayout()
        switch_row.setSpacing(6)
        self.switch_mode_button.setObjectName("RecipeActionButton")
        self.switch_mode_button.setMinimumHeight(36)
        switch_row.addWidget(self.switch_mode_button)
        self.switch_serial_input.setMinimumHeight(32)
        self.switch_serial_input.setStyleSheet(
            "QLineEdit { min-height: 32px; padding: 0 8px; border: 1px solid #d4dce7; border-radius: 6px; background: #ffffff; color: #334155; font-size: 12px; font-weight: 600; }"
        )
        switch_row.addWidget(self.switch_serial_input, 1)
        self.switch_machine_label.setStyleSheet("color: #0f766e; font-size: 14px; font-weight: 700; padding: 0 4px;")
        switch_row.addWidget(self.switch_machine_label)
        self.switch_machine_combo.setMinimumHeight(32)
        self.switch_machine_combo.setStyleSheet(
            "QComboBox { min-height: 32px; padding: 0 8px; border: 1px solid #d4dce7; border-radius: 6px; background: #ffffff; color: #0f172a; font-size: 12px; font-weight: 600; }"
        )
        switch_row.addWidget(self.switch_machine_combo, 1)
        self.switch_machine_confirm_button.setObjectName("RecipePrimaryButton")
        self.switch_machine_confirm_button.setMinimumHeight(32)
        switch_row.addWidget(self.switch_machine_confirm_button)
        control_layout.addLayout(switch_row)

        result_group = QGroupBox("检测结果")
        result_layout = QHBoxLayout(result_group)
        result_layout.setContentsMargins(10, 14, 10, 10)
        result_layout.setSpacing(10)
        result_layout.addWidget(self.result_label, 2)
        detail_grid = QGridLayout()
        detail_grid.setHorizontalSpacing(8)
        detail_grid.setVerticalSpacing(8)
        detail_grid.addWidget(self._build_result_detail_cell("耗时", self.result_duration_label), 0, 0)
        detail_grid.addWidget(self._build_result_detail_cell("触发时间", self.trigger_time_label), 0, 1)
        detail_grid.addWidget(self._build_result_detail_cell("NG 数量", self.result_ng_count_label), 1, 0)
        detail_grid.addWidget(self._build_result_detail_cell("连续 NG", self.consecutive_ng_label), 1, 1)
        result_layout.addLayout(detail_grid, 3)

        roi_group = QGroupBox("ROI 检测结果")
        roi_layout = QVBoxLayout(roi_group)
        roi_layout.setContentsMargins(8, 14, 8, 8)
        roi_layout.addWidget(self.roi_table)

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(10)
        bottom_row.addWidget(self._build_stats_panel(), 3)

        action_group = QGroupBox("操作")
        action_layout = QVBoxLayout(action_group)
        action_layout.setContentsMargins(10, 14, 10, 10)
        action_layout.setSpacing(8)
        action_layout.addWidget(self.manual_test_button)
        action_layout.addWidget(self.save_image_button)
        action_layout.addWidget(self.view_record_button)
        action_layout.addWidget(self.clear_alarm_button)
        action_layout.addStretch(1)
        bottom_row.addWidget(action_group, 2)

        layout.addWidget(control_group)
        layout.addWidget(result_group)
        layout.addWidget(self._build_camera_params_panel())
        layout.addWidget(self._build_comparison_panel())
        layout.addWidget(roi_group, 2)
        layout.addLayout(bottom_row)
        return panel

    def _build_footer_bar(self) -> QWidget:
        panel = QFrame(self)
        panel.setObjectName("FooterBar")
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(14)
        layout.addWidget(self.footer_state_label)
        layout.addWidget(self.footer_version_label)
        layout.addWidget(self.footer_user_label)
        layout.addStretch(1)
        layout.addWidget(self.footer_message_label, 2)
        return panel

    def _bind_events(self) -> None:
        self.refresh_button.clicked.connect(self._load_recipe_summaries)
        self.add_button.clicked.connect(self._create_recipe)
        self.duplicate_button.clicked.connect(self._duplicate_recipe)
        self.delete_button.clicked.connect(self._delete_recipe)
        self.recipe_combo.currentIndexChanged.connect(self._on_recipe_changed)
        self.edit_button.clicked.connect(self._open_recipe_editor)
        self.manual_test_button.clicked.connect(self._capture_manual_frame)
        self.plc_listen_button.clicked.connect(self._start_plc_listener)
        self.plc_stop_button.clicked.connect(self._stop_plc_listener)
        self.plc_trigger_button.clicked.connect(self._simulate_plc_trigger)
        self.image_fit_button.clicked.connect(lambda: self._notify_toolbar_action("图像当前为适应窗口显示"))
        self.image_fit_button.clicked.connect(self.image_canvas.fit_to_window)
        self.image_fit_button.clicked.connect(lambda: self._notify_toolbar_action("图像切换为适应窗口显示"))
        self.image_original_button.clicked.connect(self.image_canvas.show_original_size)
        self.image_original_button.clicked.connect(lambda: self._notify_toolbar_action("图像切换为原始大小显示"))
        self.image_zoom_in_button.clicked.connect(self.image_canvas.zoom_in)
        self.image_zoom_in_button.clicked.connect(lambda: self._notify_toolbar_action("图像已放大"))
        self.image_zoom_out_button.clicked.connect(self.image_canvas.zoom_out)
        self.image_zoom_out_button.clicked.connect(lambda: self._notify_toolbar_action("图像已缩小"))
        self.view_record_button.clicked.connect(self._open_record_history)
        self.save_image_button.clicked.connect(self._save_current_image)
        self.clear_alarm_button.clicked.connect(self._clear_alarm_state)
        self.camera_param_read_button.clicked.connect(self._read_camera_params)
        self.camera_param_apply_button.clicked.connect(self._apply_camera_params)
        self.switch_mode_button.clicked.connect(self._on_switch_mode_toggle)
        self.switch_machine_confirm_button.clicked.connect(self._on_manual_switch_confirm)
        self.switch_serial_input.returnPressed.connect(self._on_serial_input_return)

    def _create_recipe(self) -> None:
        try:
            recipe_document = self._recipe_controller.create_new_recipe_draft(self._current_recipe)
        except Exception as exc:
            QMessageBox.critical(self, "新增配方失败", str(exc))
            self._push_status_message(f"新增配方失败: {exc}", level="ERROR")
            return
        self._edit_recipe_document(recipe_document)

    def _duplicate_recipe(self) -> None:
        if self._current_recipe is None:
            self._push_status_message("当前无可复制配方", level="WARN")
            return
        try:
            recipe_document = self._recipe_controller.create_duplicate_recipe_draft(self._current_recipe)
        except Exception as exc:
            QMessageBox.critical(self, "复制配方失败", str(exc))
            self._push_status_message(f"复制配方失败: {exc}", level="ERROR")
            return
        self._edit_recipe_document(recipe_document)

    def _delete_recipe(self) -> None:
        if self._current_recipe is None:
            self._push_status_message("当前无可删除配方", level="WARN")
            return

        recipe = self._current_recipe.recipe
        reply = QMessageBox.question(
            self,
            "删除配方",
            f"确认删除当前配方？\n\n配方名称：{recipe.name}\n配方 ID：{recipe.id}\n\n此操作会删除配方文件，且不可撤销。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        try:
            self._recipe_controller.delete_recipe(recipe.id)
        except Exception as exc:
            QMessageBox.critical(self, "删除配方失败", str(exc))
            self._push_status_message(f"删除配方失败: {exc}", level="ERROR")
            return

        deleted_name = recipe.name
        self._load_recipe_summaries()
        self._push_status_message(f"配方已删除: {deleted_name}")

    def _load_recipe_summaries(self) -> None:
        summaries = self._recipe_controller.list_recipe_summaries()
        self.recipe_combo.blockSignals(True)
        self.recipe_combo.clear()
        for summary in summaries:
            self.recipe_combo.addItem(summary.name, summary.recipe_id)
        self.recipe_combo.blockSignals(False)

        if summaries:
            self.recipe_combo.setCurrentIndex(0)
            self._show_recipe(self._recipe_controller.get_recipe(summaries[0].recipe_id))
        else:
            self._show_recipe(None)

    def _on_recipe_changed(self, index: int) -> None:
        if index < 0:
            self._show_recipe(None)
            return
        recipe_id = self.recipe_combo.itemData(index)
        self._show_recipe(self._recipe_controller.get_recipe(recipe_id))

    def _show_recipe(self, document: Optional[RecipeDocument]) -> None:
        self._current_recipe = document
        if self._external_trigger_listening:
            self._stop_plc_listener()
        if document is None:
            self.station_label.setText("-")
            # camera_label is managed by _refresh_status_indicators — keep it stable
            self.product_label.setText("-")
            self.recipe_name_label.setText("-")
            self.current_template_info_label.setText("-")
            self.last_error_label.setText("-")
            self.roi_table.setRowCount(0)
            self.image_canvas.clear_image()
            self.image_canvas.set_roi_rects([])
            self.result_label.setText("无配方")
            self._update_parallel_comparison(None)
            self.target_cycle_label.setText("-")
            self._reset_dashboard()
            self._set_runtime_state_style("无配方", "#7c2d12", "#ffedd5")
            self._refresh_trigger_controls()
            return

        recipe = document.recipe
        template = recipe.templates[0] if recipe.templates else None

        self.recipe_name_label.setText(recipe.name)
        self.station_label.setText(recipe.station_id)
        # camera_label is managed by _refresh_status_indicators — keep it stable
        self.product_label.setText(recipe.product_name)
        self.switch_machine_label.setText(recipe.name)
        if self._app_config.switch_mode == "manual":
            idx = self.switch_machine_combo.findData(recipe.id)
            if idx >= 0:
                self.switch_machine_combo.setCurrentIndex(idx)
        self.current_template_info_label.setText(template.name if template else "-")
        self.last_error_label.setText("-")
        self.result_label.setText("待机")
        self._update_parallel_comparison(None)
        self.target_cycle_label.setText(f"{recipe.runtime.target_cycle_ms} ms")
        self._reset_dashboard()
        self._set_runtime_state_style("待机", "#1d4ed8", "#dbeafe")

        roi_items = template.roi_list if template else []
        self.roi_table.set_roi_items(roi_items)
        self.image_canvas.set_roi_rects(
            [
                {
                    "name": roi.name,
                    "x": roi.x,
                    "y": roi.y,
                    "width": roi.width,
                    "height": roi.height,
                    "color": roi.pass_color if roi.enabled else "#9ca3af",
                    "tooltip": f"{roi.name}\n阈值: {roi.threshold:.3f}\n算法: {self._algorithm_label(roi.algorithm)}",
                }
                for roi in roi_items
            ]
        )
        self._refresh_trigger_controls()
        if not self._external_trigger_listening:
            self._set_camera_params_enabled(True)
            self._apply_saved_camera_params()
        self._push_status_message(f"已加载配方: {recipe.name}")

    def _capture_manual_frame(self) -> None:
        if self._current_recipe is None:
            self._push_status_message("当前没有可用配方，无法执行手动采图", level="WARN")
            self.result_label.setText("无配方")
            return

        if self._external_trigger_listening:
            self._push_status_message("IO 触发监听运行中，请先停止监听再执行手动测试", level="WARN")
            return

        if self._inspection_thread is not None and self._inspection_thread.isRunning():
            self._push_status_message("检测任务仍在执行中，请稍候", level="WARN")
            return

        if self._app_config.switch_mode == "auto":
            serial_no = self.switch_serial_input.text().strip()
            if serial_no:
                self._try_auto_switch(serial_no)

        self.manual_test_button.setEnabled(False)
        self.plc_trigger_button.setEnabled(False)
        self._inspection_started_at = perf_counter()
        self.result_label.setText("采图中")
        self._set_runtime_state_style("手动检测中", "#92400e", "#fef3c7")
        self._start_inspection_thread(self._current_recipe, trigger_source="manual")

    def _open_recipe_editor(self) -> None:
        if self._current_recipe is None:
            self._push_status_message("当前无可编辑配方", level="WARN")
            return

        self._edit_recipe_document(self._current_recipe)

    def _edit_recipe_document(self, recipe_document: RecipeDocument) -> None:
        dialog = RecipeEditorDialog(self._recipe_controller, self._camera_controller, recipe_document, self)
        if dialog.exec_() != QDialog.Accepted:
            return

        updated_recipe_id = dialog.updated_document.recipe.id
        self._load_recipe_summaries()
        for index in range(self.recipe_combo.count()):
            if self.recipe_combo.itemData(index) == updated_recipe_id:
                self.recipe_combo.setCurrentIndex(index)
                self._show_recipe(self._recipe_controller.get_recipe(updated_recipe_id))
                break
        self._push_status_message(f"配方已保存: {dialog.updated_document.recipe.name}")

    def _start_inspection_thread(self, recipe_document: RecipeDocument, trigger_source: str) -> None:
        self._inspection_thread = QThread(self)
        self._inspection_worker = InspectionWorker(
            workflow_controller=self._inspection_workflow_controller,
            recipe_document=recipe_document,
            trigger_source=trigger_source,
            preferred_device_index=0,
        )
        self._inspection_worker.moveToThread(self._inspection_thread)

        self._inspection_thread.started.connect(self._inspection_worker.run)
        self._inspection_worker.started.connect(self._on_inspection_started)
        self._inspection_worker.finished.connect(self._on_inspection_finished)
        self._inspection_worker.timed_out.connect(self._on_inspection_timed_out)
        self._inspection_worker.failed.connect(self._on_inspection_failed)
        self._inspection_worker.finished.connect(self._inspection_thread.quit)
        self._inspection_worker.timed_out.connect(self._inspection_thread.quit)
        self._inspection_worker.failed.connect(self._inspection_thread.quit)
        self._inspection_thread.finished.connect(self._cleanup_inspection_thread)
        self._inspection_thread.start()

    def _on_inspection_started(self, message: str) -> None:
        """处理检测线程启动消息。

        IO 监听模式下检测线程会反复超时重入（~0.5s 间隔），
        ``started`` 信号频繁发出"正在等待 Line0 触发"，
        此时仅更新状态栏，不写入系统日志表，避免日志被刷屏。
        """
        if self._external_trigger_listening:
            self._push_status_message(message, log=False)
        else:
            self._push_status_message(message)

    def _on_inspection_finished(self, execution_result: InspectionExecutionResult) -> None:
        capture = execution_result.capture
        inspection_result = execution_result.inspection_result
        self._external_wait_timeout_count = 0
        self.last_error_label.setText("-")
        self.image_canvas.set_image_array(capture.frame.image)
        # camera_label is managed by _refresh_status_indicators — keep it stable
        self._apply_inspection_result(inspection_result)
        status_message = (
            f"采图与检测完成: {capture.device.display_name}, 帧号 {capture.frame.frame_number}, "
            f"结果 {inspection_result.overall_result}"
        )
        phase_summary = self._format_phase_metrics(execution_result.phase_metrics)
        if phase_summary:
            status_message = f"{status_message}; 节拍 {phase_summary}"
        if execution_result.save_message:
            status_message = f"{status_message}; {execution_result.save_message}"
            if execution_result.save_message.startswith("结果已保存: "):
                self.recent_save_path_label.setText(execution_result.save_message.replace("结果已保存: ", ""))
                self.recent_save_path_label.setStyleSheet("color: #22c55e; font-size: 11px;")
            elif execution_result.save_message.startswith("结果保存已转后台"):
                if "失败" in execution_result.save_message:
                    self.recent_save_path_label.setText("后台保存异常 ⚠️")
                    self.recent_save_path_label.setStyleSheet("color: #f59e0b; font-size: 11px; font-weight: bold;")
                else:
                    self.recent_save_path_label.setText("后台保存中")
                    self.recent_save_path_label.setStyleSheet("color: #94a3b8; font-size: 11px;")
            elif "保存失败" in execution_result.save_message:
                self.recent_save_path_label.setText("保存失败")
                self.recent_save_path_label.setStyleSheet("color: #ef4444; font-size: 11px; font-weight: bold;")
        if execution_result.plc_output_message:
            status_message = f"{status_message}; {execution_result.plc_output_message}"
        self.trigger_time_label.setText(QDateTime.currentDateTime().toString("HH:mm:ss.zzz"))
        self.result_ng_count_label.setText(
            str(sum(1 for roi_result in inspection_result.roi_results if roi_result.enabled and not roi_result.passed))
        )
        self._push_status_message(status_message)
        total_ms = execution_result.phase_metrics.get("total_ms") if execution_result.phase_metrics else None
        self._update_cycle_time_from_elapsed(total_ms)
        self._record_result(inspection_result.overall_result)
        if inspection_result.overall_result == "OK":
            self._set_runtime_state_style("检测完成 / OK", "#14532d", "#dcfce7")
        else:
            self._set_runtime_state_style("检测完成 / NG", "#991b1b", "#fee2e2")
        if self._external_trigger_listening and execution_result.trigger_source == "io":
            self.manual_test_button.setEnabled(False)
            self.plc_trigger_button.setEnabled(False)
            self.plc_label.setText("等待 Line0")
            self._set_runtime_state_style("IO触发待机", "#1d4ed8", "#dbeafe")
            self._pending_external_wait = True
        else:
            self.manual_test_button.setEnabled(True)
            self.plc_trigger_button.setEnabled(self._current_recipe is None or self._current_recipe.recipe.trigger_mode != "plc_external")

    def _on_inspection_failed(self, message: str) -> None:
        failure_title = "IO 触发失败" if self._current_recipe is not None and self._current_recipe.recipe.trigger_mode == "plc_external" else "手动测试失败"
        QMessageBox.critical(self, failure_title, message)

        self.result_label.setText("采图失败")
        self.last_error_label.setText(message)
        self.trigger_time_label.setText(QDateTime.currentDateTime().toString("HH:mm:ss.zzz"))
        self.result_ng_count_label.setText("0")
        if self._external_trigger_listening:
            self._external_trigger_listening = False
            self._pending_external_wait = False
            self._external_wait_timeout_count = 0
            self._push_status_message(f"IO 触发检测失败: {message}", level="ERROR")
        else:
            self._push_status_message(f"手动采图失败: {message}", level="ERROR")
        self._update_cycle_time()
        self._record_result("ERR")
        self._set_runtime_state_style("检测失败", "#991b1b", "#fee2e2")
        self.manual_test_button.setEnabled(True)
        self._refresh_trigger_controls()

    def _on_inspection_timed_out(self, message: str) -> None:
        if self._external_trigger_listening:
            self._external_wait_timeout_count += 1
            waited_seconds = self._external_wait_timeout_count * 0.5
            self.plc_label.setText(f"等待 Line0 ({waited_seconds:.1f}s)")
            if self._external_wait_timeout_count == 1 or self._external_wait_timeout_count % 6 == 0:
                self._push_status_message(f"IO 监听中，仍在等待 Line0 触发脉冲，已等待 {waited_seconds:.1f} s", log=False)
            self._pending_external_wait = True
            return
        self._push_status_message(message, level="WARN")

    def _cleanup_inspection_thread(self) -> None:
        if self._inspection_worker is not None:
            self._inspection_worker.deleteLater()
            self._inspection_worker = None
        if self._inspection_thread is not None:
            self._inspection_thread.deleteLater()
            self._inspection_thread = None
        if self._pending_external_wait and self._external_trigger_listening:
            self._pending_external_wait = False
            QTimer.singleShot(0, self._queue_external_trigger_wait)

    def _apply_inspection_result(self, inspection_result: InspectionResult) -> None:
        self.result_label.setText(inspection_result.overall_result)
        if inspection_result.overall_result == "OK":
            self.result_label.setStyleSheet(
                "font-size: 34px; font-weight: bold; color: #14532d; background: #dcfce7;"
                "padding: 18px; border-radius: 8px;"
            )
        else:
            self.result_label.setStyleSheet(
                "font-size: 34px; font-weight: bold; color: #7f1d1d; background: #fee2e2;"
                "padding: 18px; border-radius: 8px;"
            )

        self.roi_table.set_result_items(inspection_result.roi_results)
        self._update_parallel_comparison(inspection_result)
        self.image_canvas.set_roi_rects(
            [
                {
                    "name": result.roi_name,
                    "x": result.bbox.x,
                    "y": result.bbox.y,
                    "width": result.bbox.width,
                    "height": result.bbox.height,
                    "color": "#22c55e" if result.passed else "#ff3b30",
                    "tooltip": (
                        f"{result.roi_name}\n"
                        f"状态: {'OK' if result.passed else 'NG'}\n"
                        f"阈值: {result.threshold:.3f}\n"
                        f"算法: {self._algorithm_label(result.algorithm)}\n"
                        f"分值: {'-' if result.score is None else f'{result.score:.3f}'}"
                        f"{'\n预测: ' + result.predicted_label if result.predicted_label else ''}"
                        f"{'\n置信度: ' + format(result.confidence, '.3f') if result.confidence is not None else ''}"
                        f"{'\n并行算法: ' + self._algorithm_label(result.parallel_algorithm) if result.parallel_algorithm else ''}"
                        f"{'\n并行分值: ' + format(result.parallel_score, '.3f') if result.parallel_score is not None else ''}"
                        f"{'\n并行预测: ' + result.parallel_predicted_label if result.parallel_predicted_label else ''}"
                    ),
                }
                for result in inspection_result.roi_results
            ]
        )

    def _update_parallel_comparison(self, inspection_result: InspectionResult | None) -> None:
        if inspection_result is None:
            self.compare_primary_label.setText("-")
            self.compare_shadow_label.setText("-")
            self.compare_summary_label.setText("当前配方未启用并行对照")
            return

        parallel_results = [item for item in inspection_result.roi_results if item.parallel_algorithm]
        if not parallel_results:
            self.compare_primary_label.setText("规则法")
            self.compare_shadow_label.setText("未启用")
            self.compare_summary_label.setText("当前检测未启用并行对照")
            return

        primary_algorithms = sorted({self._algorithm_label(item.algorithm) for item in parallel_results if item.algorithm})
        shadow_algorithms = sorted({self._algorithm_label(item.parallel_algorithm) for item in parallel_results if item.parallel_algorithm})
        diff_count = sum(1 for item in parallel_results if item.parallel_passed is not None and item.parallel_passed != item.passed)
        shadow_ng_count = sum(1 for item in parallel_results if item.parallel_passed is False)
        first_diff = next((item for item in parallel_results if item.parallel_passed is not None and item.parallel_passed != item.passed), None)

        self.compare_primary_label.setText(" / ".join(primary_algorithms) or "-")
        self.compare_shadow_label.setText(" / ".join(shadow_algorithms) or "-")

        summary_parts = [
            f"参与对照 ROI: {len(parallel_results)}",
            f"差异数: {diff_count}",
            f"并行 NG: {shadow_ng_count}",
        ]
        if first_diff is not None:
            summary_parts.append(
                f"首个差异: {first_diff.roi_name} 主判定 {'OK' if first_diff.passed else 'NG'} / 并行 {'OK' if first_diff.parallel_passed else 'NG'}"
            )
        self.compare_summary_label.setText("；".join(summary_parts))

    def _start_plc_listener(self) -> None:
        if self._current_recipe is not None and self._current_recipe.recipe.trigger_mode == "plc_external":
            self._start_external_trigger_listener()
            return
        if self._plc_thread is not None and self._plc_thread.isRunning():
            self._push_status_message("PLC 监听已在运行", level="WARN")
            return
        try:
            self._plc_controller.connect()
        except Exception as exc:
            self.plc_label.setText("连接失败")
            self._push_status_message(f"PLC 连接失败: {exc}", level="ERROR")
            return

        self._plc_thread = QThread(self)
        self._plc_worker = PlcListenerWorker(self._plc_controller)
        self._plc_worker.moveToThread(self._plc_thread)

        self._plc_thread.started.connect(self._plc_worker.run)
        self._plc_worker.status_changed.connect(self._on_plc_status_changed)
        self._plc_worker.trigger_received.connect(self._on_plc_trigger_received)
        self._plc_worker.failed.connect(self._on_plc_listener_failed)
        self._plc_worker.finished.connect(self._plc_thread.quit)
        self._plc_thread.finished.connect(self._cleanup_plc_thread)
        self._plc_thread.start()
        self.plc_label.setText("监听中")
        self._set_runtime_state_style("PLC监听中", "#1d4ed8", "#dbeafe")
        self._push_status_message("PLC 监听线程已启动")

    def _start_external_trigger_listener(self) -> None:
        if self._external_trigger_listening:
            self._push_status_message("IO 监听已在运行", level="WARN")
            return
        if self._current_recipe is None:
            self._push_status_message("当前无有效配方，无法启动 IO 监听", level="WARN")
            return
        if self._inspection_thread is not None and self._inspection_thread.isRunning():
            self._push_status_message("当前检测任务仍在执行中，暂不能启动 IO 监听", level="WARN")
            return

        try:
            self._camera_controller.set_trigger_activation(self._app_config.camera_params.trigger_activation)
            _logger.info("_start_external_trigger_listener: trigger_activation=%s", self._app_config.camera_params.trigger_activation)
            device_name = self._camera_controller.prepare_external_trigger_listener(preferred_device_index=0)
            _logger.info("_start_external_trigger_listener: device ready, name=%s", device_name)
        except Exception as exc:
            self.last_error_label.setText(str(exc))
            self._push_status_message(f"启动 IO 监听失败: {exc}", level="ERROR")
            QMessageBox.critical(self, "启动 IO 监听失败", str(exc))
            return

        self._external_trigger_listening = True
        self._pending_external_wait = False
        self._external_wait_timeout_count = 0
        self.manual_test_button.setEnabled(False)
        self.plc_trigger_button.setEnabled(False)
        self._set_camera_params_enabled(False)
        self.plc_label.setText("等待 Line0")
        self.result_label.setText("等待触发")
        # camera_label is managed by _refresh_status_indicators — keep it stable
        self._set_runtime_state_style("IO触发待机", "#1d4ed8", "#dbeafe")
        self._push_status_message(f"相机外部 IO 监听已启动: {device_name}，等待 Line0 触发")
        self._queue_external_trigger_wait()

    def _queue_external_trigger_wait(self) -> None:
        if not self._external_trigger_listening or self._current_recipe is None:
            _logger.debug("_queue_external_trigger_wait: skipped (listening=%s recipe=%s)",
                          self._external_trigger_listening, self._current_recipe is not None)
            return
        if self._inspection_thread is not None and self._inspection_thread.isRunning():
            _logger.debug("_queue_external_trigger_wait: skipped (thread still running)")
            return
        _logger.info("_queue_external_trigger_wait: starting IO inspection (timeout_count=%d)",
                     self._external_wait_timeout_count)
        if self._app_config.switch_mode == "auto":
            serial_no = self.switch_serial_input.text().strip()
            if serial_no:
                self._try_auto_switch(serial_no)
        self.result_label.setText("等待触发")
        self._start_inspection_thread(self._current_recipe, trigger_source="io")

    def _stop_plc_listener(self) -> None:
        if self._external_trigger_listening:
            self._external_trigger_listening = False
            self._pending_external_wait = False
            self._external_wait_timeout_count = 0
            self._set_camera_params_enabled(True)
            self.plc_label.setText("待机")
            if self._current_recipe is not None:
                self._set_runtime_state_style("待机", "#1d4ed8", "#dbeafe")
            self.manual_test_button.setEnabled(True)
            self._refresh_trigger_controls()
            self._push_status_message("IO 监听已停止")
            return
        if self._plc_worker is not None:
            self._plc_worker.stop()
        try:
            self._plc_controller.disconnect()
        except Exception as exc:
            self._push_status_message(f"停止 PLC 监听失败: {exc}", level="ERROR")
        if self._plc_thread is not None and self._plc_thread.isRunning():
            self._plc_thread.quit()
            self._plc_thread.wait(1500)
        self.plc_label.setText("未连接")
        if self._current_recipe is not None:
            self._set_runtime_state_style("待机", "#1d4ed8", "#dbeafe")
        self._push_status_message("PLC 监听已停止")

    def _simulate_plc_trigger(self) -> None:
        if self._current_recipe is not None and self._current_recipe.recipe.trigger_mode == "plc_external":
            self._push_status_message("当前配方为相机 IO 模式，请通过 Line0 硬件脉冲触发", level="WARN")
            return
        try:
            self._plc_controller.simulate_trigger()
            self._push_status_message("已发送模拟 PLC 触发")
        except Exception as exc:
            self._push_status_message(f"模拟 PLC 触发失败: {exc}", level="ERROR")

    def _on_plc_status_changed(self, message: str) -> None:
        self.plc_label.setText(message)
        self._push_status_message(message)

    def _on_plc_trigger_received(self, message: str) -> None:
        self._push_status_message(message)
        if self._current_recipe is None:
            self._push_status_message("收到 PLC 触发，但当前无有效配方", level="WARN")
            return
        if self._inspection_thread is not None and self._inspection_thread.isRunning():
            self._push_status_message("收到 PLC 触发，但检测任务仍在执行中，本次触发已忽略", level="WARN")
            return
        self.manual_test_button.setEnabled(False)
        self.plc_trigger_button.setEnabled(False)
        self._inspection_started_at = perf_counter()
        self.result_label.setText("PLC触发")
        self.trigger_time_label.setText(QDateTime.currentDateTime().toString("HH:mm:ss.zzz"))
        self._set_runtime_state_style("PLC触发检测中", "#92400e", "#fef3c7")
        self._start_inspection_thread(self._current_recipe, trigger_source="plc")

    def _on_plc_listener_failed(self, message: str) -> None:
        self.plc_label.setText("异常")
        self.last_error_label.setText(message)
        self._set_runtime_state_style("PLC异常", "#991b1b", "#fee2e2")
        self._push_status_message(f"PLC 监听异常: {message}", level="ERROR")

    def _cleanup_plc_thread(self) -> None:
        if self._plc_worker is not None:
            self._plc_worker.deleteLater()
            self._plc_worker = None
        if self._plc_thread is not None:
            self._plc_thread.deleteLater()
            self._plc_thread = None

    def _refresh_trigger_controls(self) -> None:
        io_mode = self._current_recipe is not None and self._current_recipe.recipe.trigger_mode == "plc_external"
        if io_mode:
            self.plc_listen_button.setText("启动 IO 监听")
            self.plc_stop_button.setText("停止 IO 监听")
            self.plc_trigger_button.setText("硬件触发")
            self.plc_trigger_button.setEnabled(False)
            if not self._external_trigger_listening:
                self.plc_label.setText("待机")
            self._set_camera_params_enabled(not self._external_trigger_listening)
            return

        self.plc_listen_button.setText("启动 PLC 监听")
        self.plc_stop_button.setText("停止 PLC 监听")
        self.plc_trigger_button.setText("模拟 PLC 触发")
        self.plc_trigger_button.setEnabled(True)
        if self._plc_thread is None or not self._plc_thread.isRunning():
            self.plc_label.setText("未连接")
        self._set_camera_params_enabled(True)

    def _set_camera_params_enabled(self, enabled: bool) -> None:
        for widget in self.camera_param_widgets:
            widget.setEnabled(enabled)
        if enabled:
            self.camera_param_status_label.setText("")
        else:
            self.camera_param_status_label.setText("IO 监听运行中，参数已锁定")
            self.camera_param_status_label.setStyleSheet("color: #f59e0b; font-size: 11px; padding: 2px;")

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._external_trigger_listening:
            reply = QMessageBox.warning(
                self,
                "确认退出",
                "IO 监听正在运行中，退出将停止在线检测！\n\n确定要退出视觉检测软件吗？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
        else:
            reply = QMessageBox.question(
                self,
                "确认退出",
                "确定要退出视觉检测软件吗？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
        if reply != QMessageBox.Yes:
            event.ignore()
            return

        self._save_camera_params_to_config()
        if self._inspection_thread is not None and self._inspection_thread.isRunning():
            self._inspection_thread.quit()
            self._inspection_thread.wait(2000)
        self._stop_plc_listener()
        self._camera_controller.shutdown()
        # 等待后台图片保存任务完成，防止退出时丢失未保存的图片
        self._inspection_workflow_controller.shutdown(timeout_seconds=5.0)
        super().closeEvent(event)
