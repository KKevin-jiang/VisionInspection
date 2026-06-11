from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path

import numpy as np
from PyQt5.QtGui import QImage
from PyQt5.QtCore import Qt, QRect
from PyQt5.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStyledItemDelegate,
    QStyle,
    QStyleOptionButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from vision_inspection.application.controllers.camera_controller import CameraController
from vision_inspection.application.controllers.recipe_controller import RecipeController
from vision_inspection.domain.models.recipe import RecipeDocument, RoiConfig, TemplateConfig
from vision_inspection.ui.ai_classifier_config_dialog import AiClassifierConfigDialog
from vision_inspection.ui.binary_ratio_config_dialog import BinaryRatioConfigDialog
from vision_inspection.ui.widgets.image_canvas import ImageCanvas

try:
    import cv2
except ImportError:
    cv2 = None


class CenteredCheckStateDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index) -> None:
        check_state = index.data(Qt.CheckStateRole)
        if check_state is None:
            super().paint(painter, option, index)
            return

        button_option = QStyleOptionButton()
        button_option.state |= QStyle.State_Enabled
        if int(check_state) == int(Qt.Checked):
            button_option.state |= QStyle.State_On
        else:
            button_option.state |= QStyle.State_Off

        indicator_rect = QApplication.style().subElementRect(QStyle.SE_CheckBoxIndicator, button_option, None)
        button_option.rect = QRect(
            option.rect.x() + (option.rect.width() - indicator_rect.width()) // 2,
            option.rect.y() + (option.rect.height() - indicator_rect.height()) // 2,
            indicator_rect.width(),
            indicator_rect.height(),
        )
        QApplication.style().drawControl(QStyle.CE_CheckBox, button_option, painter)

    def editorEvent(self, event, model, option, index) -> bool:
        if not (index.flags() & Qt.ItemIsUserCheckable) or not (index.flags() & Qt.ItemIsEnabled):
            return False
        if event.type() == event.MouseButtonRelease:
            current_state = index.data(Qt.CheckStateRole)
            next_state = Qt.Unchecked if int(current_state) == int(Qt.Checked) else Qt.Checked
            return model.setData(index, next_state, Qt.CheckStateRole)
        if event.type() == event.KeyPress and event.key() in {Qt.Key_Space, Qt.Key_Select, Qt.Key_Return, Qt.Key_Enter}:
            current_state = index.data(Qt.CheckStateRole)
            next_state = Qt.Unchecked if int(current_state) == int(Qt.Checked) else Qt.Checked
            return model.setData(index, next_state, Qt.CheckStateRole)
        return False


class RecipeEditorDialog(QDialog):
    def __init__(
        self,
        recipe_controller: RecipeController,
        camera_controller: CameraController,
        recipe_document: RecipeDocument,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._recipe_controller = recipe_controller
        self._camera_controller = camera_controller
        self._document = deepcopy(recipe_document)
        self._active_template_index = 0
        self._template_images: dict[int, np.ndarray | None] = {}

        self.setWindowTitle(f"配方编辑 - {self._document.recipe.name}")
        self._apply_initial_window_size()

        self._build_widgets()
        self._apply_dialog_style()
        self._build_layout()
        self._bind_events()
        self._load_document()

    ROI_ALGORITHM_OPTIONS = ["binary_gray_ratio", "ssim", "ai_classifier"]
    ROI_ALGORITHM_LABELS = {
        "binary_gray_ratio": "二值化灰度面积比",
        "ssim": "结构相似度",
        "ai_classifier": "AI 分类器",
    }

    @property
    def updated_document(self) -> RecipeDocument:
        return self._document

    def _apply_dialog_style(self) -> None:
        self.setStyleSheet(
            "QDialog { background: #eef1f5; }"
            "QFrame#HeaderCard { background: #101722; border: 1px solid #1f2937; border-radius: 12px; }"
            "QFrame#FooterCard { background: #ffffff; border: 1px solid #dde5ef; border-radius: 12px; }"
            "QGroupBox { font-weight: 600; border: 1px solid #dde5ef; border-radius: 10px; margin-top: 10px; background: #ffffff; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: #0f172a; }"
            "QLabel { color: #111827; }"
            "QLineEdit, QComboBox, QSpinBox, QTextEdit, QTableWidget { background: #ffffff; border: 1px solid #d4dce7; border-radius: 6px; }"
            "QLineEdit, QComboBox, QSpinBox { min-height: 32px; padding: 0 8px; }"
            "QComboBox#TemplateSelector { min-height: 36px; padding: 0 36px 0 12px; border: 1px solid #cfd8e3; border-radius: 8px; background: #f8fafc; color: #0f172a; font-size: 13px; font-weight: 600; }"
            "QComboBox#TemplateSelector:hover { background: #f3f7fb; border-color: #b8c7d9; }"
            "QComboBox#TemplateSelector:focus { border-color: #7c9cc2; background: #ffffff; }"
            "QComboBox#TemplateSelector::drop-down { subcontrol-origin: padding; subcontrol-position: top right; width: 28px; border-left: 1px solid #dde5ef; background: #f1f5f9; border-top-right-radius: 8px; border-bottom-right-radius: 8px; }"
            "QComboBox#TemplateSelector QAbstractItemView { border: 1px solid #d7e0ea; background: #ffffff; selection-background-color: #dbeafe; selection-color: #0f172a; outline: 0; padding: 4px; }"
            "QComboBox#RoiAlgorithmSelector { min-height: 30px; padding: 0 30px 0 10px; border: 1px solid #d7e0ea; border-radius: 7px; background: #f8fafc; color: #334155; font-size: 12px; font-weight: 600; }"
            "QComboBox#RoiAlgorithmSelector:hover { background: #f3f7fb; border-color: #bfd0e0; }"
            "QComboBox#RoiAlgorithmSelector:focus { border-color: #8eabc8; background: #ffffff; }"
            "QComboBox#RoiAlgorithmSelector::drop-down { subcontrol-origin: padding; subcontrol-position: top right; width: 24px; border-left: 1px solid #dde5ef; background: #f1f5f9; border-top-right-radius: 7px; border-bottom-right-radius: 7px; }"
            "QComboBox#RoiAlgorithmSelector QAbstractItemView { border: 1px solid #d7e0ea; background: #ffffff; selection-background-color: #dbeafe; selection-color: #0f172a; outline: 0; }"
            "QPushButton { min-height: 32px; padding: 0 12px; border: 1px solid #d4dce7; border-radius: 6px; background: #f9fbfd; color: #111827; }"
            "QPushButton:hover { background: #f0f5fa; }"
            "QTabWidget::pane { border: 1px solid #dde5ef; border-radius: 10px; background: #ffffff; top: -1px; }"
            "QTabBar::tab { min-width: 110px; min-height: 34px; margin-right: 6px; padding: 0 12px; background: #e8edf4; color: #475569; border-top-left-radius: 8px; border-top-right-radius: 8px; }"
            "QTabBar::tab:selected { background: #ffffff; color: #0f172a; font-weight: 700; }"
            "QHeaderView::section { background: #f8fafc; color: #475569; padding: 6px; border: none; border-bottom: 1px solid #e2e8f0; font-weight: 600; }"
        )

    def _build_widgets(self) -> None:
        self.header_title_label = QLabel("配方编辑")
        self.header_title_label.setStyleSheet("color: #eef6ff; font-size: 22px; font-weight: 700;")
        self.header_subtitle_label = QLabel("维护当前配方、模板、ROI、检测策略与存储参数")
        self.header_subtitle_label.setStyleSheet("color: #aebfd5; font-size: 13px;")
        self.header_recipe_label = QLabel(self._document.recipe.name or "未命名配方")
        self.header_recipe_label.setStyleSheet("color: #7ee081; font-size: 14px; font-weight: 700;")
        self.tabs = QTabWidget(self)

        self.recipe_id_edit = QLineEdit()
        self.recipe_code_edit = QLineEdit()
        self.recipe_name_edit = QLineEdit()
        self.product_name_edit = QLineEdit()
        self.product_model_edit = QLineEdit()
        self.station_id_edit = QLineEdit()
        self.camera_id_edit = QLineEdit()
        self.recipe_enabled_check = QCheckBox("启用配方")
        self.trigger_mode_combo = QComboBox()
        self.trigger_mode_combo.addItems(["manual", "plc_external", "software_trigger"])
        self.template_match_mode_combo = QComboBox()
        self.template_match_mode_combo.addItems(["single_active", "priority", "multi_template"])
        self.description_edit = QTextEdit()
        self.description_edit.setFixedHeight(90)

        self.template_combo = QComboBox()
        self.template_combo.setObjectName("TemplateSelector")
        self.template_code_edit = QLineEdit()
        self.template_name_edit = QLineEdit()
        self.template_enabled_check = QCheckBox("启用模板")
        self.template_default_check = QCheckBox("默认模板")
        self.template_image_path_edit = QLineEdit()
        self.template_width_spin = QSpinBox()
        self.template_width_spin.setRange(0, 10000)
        self.template_height_spin = QSpinBox()
        self.template_height_spin.setRange(0, 10000)
        self.template_description_edit = QTextEdit()
        self.template_description_edit.setFixedHeight(70)

        self.add_roi_button = QPushButton("新增 ROI")
        self.remove_roi_button = QPushButton("删除 ROI")
        self.configure_binary_button = QPushButton("二值化设置")
        self.configure_ai_button = QPushButton("AI 设置")
        self.capture_template_button = QPushButton("拍摄模板图")
        self.reload_template_button = QPushButton("重载模板图")
        self.remove_roi_button.setEnabled(False)
        self.configure_binary_button.setEnabled(False)
        self.configure_ai_button.setEnabled(False)
        self.roi_table = QTableWidget(0, 6)
        self.roi_table.setHorizontalHeaderLabels(["启用", "名称", "阈值", "算法", "参数", "说明"])
        self.roi_table.verticalHeader().setVisible(False)
        self.roi_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.roi_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.roi_table.setItemDelegateForColumn(0, CenteredCheckStateDelegate(self.roi_table))
        self.roi_table.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.roi_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.roi_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.roi_table.setColumnWidth(1, 96)
        self.roi_table.setColumnWidth(2, 60)
        self.roi_table.setColumnWidth(3, 180)
        self.roi_table.setColumnWidth(5, 150)
        self.roi_workflow_hint_label = QLabel(
            "建议流程：1. 拍摄或加载模板图  2. 在图上框选 ROI  3. 在列表中选中 ROI  4. 点击“二值化设置”做可视化调参  5. 保存配方"
        )
        self.roi_workflow_hint_label.setWordWrap(True)
        self.roi_workflow_hint_label.setStyleSheet(
            "padding: 10px 12px; background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 8px; color: #1e3a8a;"
        )
        self.roi_parameter_hint_label = QLabel(
            "参数列现在显示的是摘要。二值化参数建议通过“二值化设置”窗口调整，而不是直接修改底层数据。"
        )
        self.roi_parameter_hint_label.setWordWrap(True)
        self.roi_parameter_hint_label.setStyleSheet("color: #475569; padding: 4px 0 0 0;")
        self.template_canvas = ImageCanvas()
        self.template_canvas.set_editable(True)
        self.template_canvas.set_placeholder_text("模板图编辑区\n点击“拍摄模板图”后可直接在图上框选检测 ROI")

        self.decision_mode_combo = QComboBox()
        self.decision_mode_combo.addItems(["all_roi_pass", "min_pass_count"])
        self.min_pass_count_spin = QSpinBox()
        self.min_pass_count_spin.setRange(0, 999)
        self.allow_disabled_roi_check = QCheckBox("允许禁用 ROI")
        self.final_ng_any_fail_check = QCheckBox("任一失败即 NG")
        self.grayscale_check = QCheckBox("灰度化")
        self.denoise_check = QCheckBox("去噪")
        self.normalize_check = QCheckBox("归一化")
        self.denoise_method_combo = QComboBox()
        self.denoise_method_combo.addItems(["gaussian", "median", "bilateral"])
        self.resize_mode_combo = QComboBox()
        self.resize_mode_combo.addItems(["keep_roi_size", "fit_template"])
        self.blur_kernel_spin = QSpinBox()
        self.blur_kernel_spin.setRange(1, 99)
        self.blur_kernel_spin.setSingleStep(2)

        self.strategy_intro_label = QLabel()
        self.strategy_intro_label.setWordWrap(True)
        self.strategy_intro_label.setStyleSheet(
            "padding: 10px 12px; background: #f8fafc; border: 1px solid #dbe4ee; border-radius: 8px; color: #334155;"
        )
        self.plc_group = QGroupBox()
        self.plc_enabled_label = QLabel()
        self.plc_trigger_source_label = QLabel()
        self.plc_protocol_label = QLabel()
        self.plc_timeout_label = QLabel()
        self.ng_output_enabled_label = QLabel()
        self.ng_signal_name_label = QLabel()
        self.ng_channel_label = QLabel()
        self.ng_pulse_label = QLabel("脉宽 ms")
        self.ng_delay_label = QLabel("延时 ms")
        self.ng_reset_mode_label = QLabel("复位模式")

        self.plc_enabled_check = QCheckBox("启用 PLC")
        self.plc_trigger_source_combo = QComboBox()
        self.plc_trigger_source_combo.addItems(["plc", "manual", "hybrid"])
        self.plc_protocol_edit = QLineEdit()
        self.plc_timeout_spin = QSpinBox()
        self.plc_timeout_spin.setRange(0, 60000)
        self.ng_output_enabled_check = QCheckBox("启用 NG 输出")
        self.ng_signal_name_edit = QLineEdit()
        self.ng_channel_edit = QLineEdit()
        self.ng_pulse_spin = QSpinBox()
        self.ng_pulse_spin.setRange(0, 10000)
        self.ng_delay_spin = QSpinBox()
        self.ng_delay_spin.setRange(0, 10000)
        self.ng_reset_mode_combo = QComboBox()
        self.ng_reset_mode_combo.addItems(["auto", "manual"])
        self.ng_channel_edit.setPlaceholderText("Line1")
        self.ng_signal_name_edit.setPlaceholderText("例如：检测NG回传")
        self.plc_protocol_edit.setPlaceholderText("例如：MC / Modbus / pending")

        self.storage_root_dir_edit = QLineEdit()
        self.save_raw_image_check = QCheckBox("保存原图")
        self.save_result_image_check = QCheckBox("保存结果图")
        self.save_only_ng_image_check = QCheckBox("仅保存 NG 图")
        self.save_json_record_check = QCheckBox("保存 JSON 记录")
        self.save_csv_summary_check = QCheckBox("保存 CSV 汇总")
        self.recipe_subdir_mode_combo = QComboBox()
        self.recipe_subdir_mode_combo.addItems(["by_recipe", "flat"])
        self.date_subdir_mode_combo = QComboBox()
        self.date_subdir_mode_combo.addItems(["by_day", "flat"])
        self.retention_days_spin = QSpinBox()
        self.retention_days_spin.setRange(0, 3650)

        self.target_cycle_spin = QSpinBox()
        self.target_cycle_spin.setRange(0, 60000)
        self.detection_timeout_spin = QSpinBox()
        self.detection_timeout_spin.setRange(0, 60000)
        self.retry_capture_spin = QSpinBox()
        self.retry_capture_spin.setRange(0, 20)
        self.allow_manual_test_check = QCheckBox("允许手动测试")

        self.button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)

    def _build_layout(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(10)

        header_card = QFrame(self)
        header_card.setObjectName("HeaderCard")
        header_layout = QHBoxLayout(header_card)
        header_layout.setContentsMargins(16, 14, 16, 14)
        header_layout.setSpacing(10)
        header_text_layout = QVBoxLayout()
        header_text_layout.setSpacing(2)
        header_text_layout.addWidget(self.header_title_label)
        header_text_layout.addWidget(self.header_subtitle_label)
        header_layout.addLayout(header_text_layout)
        header_layout.addStretch(1)
        header_layout.addWidget(self.header_recipe_label)

        footer_card = QFrame(self)
        footer_card.setObjectName("FooterCard")
        footer_layout = QHBoxLayout(footer_card)
        footer_layout.setContentsMargins(12, 10, 12, 10)
        footer_layout.addStretch(1)
        footer_layout.addWidget(self.button_box)

        root_layout.addWidget(header_card)
        root_layout.addWidget(self.tabs)
        root_layout.addWidget(footer_card)

        self.tabs.addTab(self._wrap_scrollable_tab(self._build_basic_tab()), "基础信息")
        self.tabs.addTab(self._wrap_scrollable_tab(self._build_template_tab()), "模板与 ROI")
        self.tabs.addTab(self._wrap_scrollable_tab(self._build_strategy_tab()), "检测与PLC")
        self.tabs.addTab(self._wrap_scrollable_tab(self._build_storage_tab()), "存储与运行")

    def _apply_initial_window_size(self) -> None:
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            self.resize(1320, 860)
            return

        available_geometry = screen.availableGeometry()
        width = min(1320, max(960, available_geometry.width() - 80))
        height = min(860, max(680, available_geometry.height() - 80))
        self.resize(width, height)

    def _wrap_scrollable_tab(self, content: QWidget) -> QScrollArea:
        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setWidget(content)
        return scroll_area

    def _build_basic_tab(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        intro_label = QLabel("填写配方名称、产品和触发模式即可，其他字段可选。完整的 ROI 和检测参数请在「模板与 ROI」页面配置。")
        intro_label.setWordWrap(True)
        intro_label.setStyleSheet("padding: 10px 12px; background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 8px; color: #1e3a8a;")

        form_group = QGroupBox("配方基础信息")
        form = QFormLayout(form_group)
        form.setContentsMargins(14, 16, 14, 12)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)
        form.addRow("配方名称", self.recipe_name_edit)

        row1 = QHBoxLayout()
        row1.setSpacing(10)
        row1.addWidget(self.product_name_edit)
        row1.addWidget(self.product_model_edit)
        form.addRow("产品名称 / 型号", row1)

        row2 = QHBoxLayout()
        row2.setSpacing(10)
        row2.addWidget(self.station_id_edit)
        row2.addWidget(self.camera_id_edit)
        form.addRow("工位 / 相机 ID", row2)

        form.addRow("触发模式", self.trigger_mode_combo)
        form.addRow("", self.recipe_enabled_check)

        layout.addWidget(intro_label)
        layout.addWidget(form_group)
        layout.addStretch(1)
        return page

    def _build_template_tab(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        intro_label = QLabel("建议按“选模板 -> 拍摄或加载模板图 -> 框选 ROI -> 选中 ROI 调参数 -> 保存”的顺序操作。")
        intro_label.setWordWrap(True)
        intro_label.setStyleSheet("padding: 10px 12px; background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 8px; color: #1e3a8a;")

        template_group = QGroupBox("模板信息")
        template_layout = QGridLayout(template_group)
        template_layout.setContentsMargins(14, 16, 14, 12)
        template_layout.setHorizontalSpacing(10)
        template_layout.setVerticalSpacing(8)
        template_layout.addWidget(QLabel("当前模板"), 0, 0)
        template_layout.addWidget(self.template_combo, 0, 1, 1, 3)
        template_layout.addWidget(QLabel("模板编号"), 1, 0)
        template_layout.addWidget(self.template_code_edit, 1, 1)
        template_layout.addWidget(QLabel("模板名称"), 1, 2)
        template_layout.addWidget(self.template_name_edit, 1, 3)
        template_layout.addWidget(self.template_enabled_check, 2, 0)
        template_layout.addWidget(self.template_default_check, 2, 1)
        template_layout.addWidget(QLabel("模板图路径"), 3, 0)
        template_layout.addWidget(self.template_image_path_edit, 3, 1, 1, 3)
        template_layout.addWidget(QLabel("宽度"), 4, 0)
        template_layout.addWidget(self.template_width_spin, 4, 1)
        template_layout.addWidget(QLabel("高度"), 4, 2)
        template_layout.addWidget(self.template_height_spin, 4, 3)
        template_layout.addWidget(QLabel("描述"), 5, 0)
        template_layout.addWidget(self.template_description_edit, 5, 1, 1, 3)

        canvas_group = QGroupBox("模板图与 ROI 框选")
        canvas_layout = QVBoxLayout(canvas_group)
        canvas_layout.setContentsMargins(12, 16, 12, 12)
        canvas_layout.setSpacing(8)
        canvas_toolbar = QHBoxLayout()
        canvas_toolbar.addWidget(self.capture_template_button)
        canvas_toolbar.addWidget(self.reload_template_button)
        canvas_toolbar.addWidget(self.add_roi_button)
        canvas_toolbar.addWidget(self.remove_roi_button)
        canvas_toolbar.addWidget(self.configure_binary_button)
        canvas_toolbar.addWidget(self.configure_ai_button)
        canvas_toolbar.addStretch(1)
        canvas_layout.addLayout(canvas_toolbar)
        canvas_layout.addWidget(self.roi_workflow_hint_label)
        canvas_layout.addWidget(self.template_canvas, 1)

        roi_group = QGroupBox("ROI 列表与参数摘要")
        roi_layout = QVBoxLayout(roi_group)
        roi_layout.setContentsMargins(12, 16, 12, 12)
        roi_layout.setSpacing(8)
        roi_layout.addWidget(self.roi_parameter_hint_label)
        roi_layout.addWidget(self.roi_table)

        content_row = QHBoxLayout()
        content_row.setSpacing(10)
        content_row.addWidget(canvas_group, 3)
        content_row.addWidget(roi_group, 2)

        layout.addWidget(intro_label)
        layout.addWidget(template_group)
        layout.addLayout(content_row, 1)
        return page

    def _build_strategy_tab(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        preprocess_group = QGroupBox("检测策略")
        preprocess_form = QFormLayout(preprocess_group)
        preprocess_form.setContentsMargins(14, 16, 14, 12)
        preprocess_form.setHorizontalSpacing(10)
        preprocess_form.setVerticalSpacing(8)
        preprocess_form.addRow("判定模式", self.decision_mode_combo)
        preprocess_form.addRow("最少通过数", self.min_pass_count_spin)
        preprocess_form.addRow("禁用 ROI 策略", self.allow_disabled_roi_check)
        preprocess_form.addRow("最终 NG 策略", self.final_ng_any_fail_check)
        preprocess_form.addRow("灰度化", self.grayscale_check)
        preprocess_form.addRow("去噪", self.denoise_check)
        preprocess_form.addRow("去噪方法", self.denoise_method_combo)
        preprocess_form.addRow("归一化", self.normalize_check)
        preprocess_form.addRow("尺寸策略", self.resize_mode_combo)
        preprocess_form.addRow("模糊核", self.blur_kernel_spin)

        plc_form = QFormLayout(self.plc_group)
        plc_form.setContentsMargins(14, 16, 14, 12)
        plc_form.setHorizontalSpacing(10)
        plc_form.setVerticalSpacing(8)
        plc_form.addRow(self.plc_enabled_label, self.plc_enabled_check)
        plc_form.addRow(self.plc_trigger_source_label, self.plc_trigger_source_combo)
        plc_form.addRow(self.plc_protocol_label, self.plc_protocol_edit)
        plc_form.addRow(self.plc_timeout_label, self.plc_timeout_spin)
        plc_form.addRow(self.ng_output_enabled_label, self.ng_output_enabled_check)
        plc_form.addRow(self.ng_signal_name_label, self.ng_signal_name_edit)
        plc_form.addRow(self.ng_channel_label, self.ng_channel_edit)
        plc_form.addRow(self.ng_pulse_label, self.ng_pulse_spin)
        plc_form.addRow(self.ng_delay_label, self.ng_delay_spin)
        plc_form.addRow(self.ng_reset_mode_label, self.ng_reset_mode_combo)

        content_row = QHBoxLayout()
        content_row.setSpacing(10)
        content_row.addWidget(preprocess_group, 1)
        content_row.addWidget(self.plc_group, 1)

        layout.addWidget(self.strategy_intro_label)
        layout.addLayout(content_row)
        layout.addStretch(1)
        return page

    def _build_storage_tab(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        intro_label = QLabel("用于配置图片留档、结果记录和运行节拍。建议在正式上线前确认目录、保留策略和节拍限制。")
        intro_label.setWordWrap(True)
        intro_label.setStyleSheet("padding: 10px 12px; background: #f8fafc; border: 1px solid #dbe4ee; border-radius: 8px; color: #334155;")

        storage_group = QGroupBox("存储策略")
        storage_form = QFormLayout(storage_group)
        storage_form.setContentsMargins(14, 16, 14, 12)
        storage_form.setHorizontalSpacing(10)
        storage_form.setVerticalSpacing(8)
        storage_form.addRow("根目录", self.storage_root_dir_edit)
        storage_form.addRow("保存原图", self.save_raw_image_check)
        storage_form.addRow("保存结果图", self.save_result_image_check)
        storage_form.addRow("仅保存 NG 图", self.save_only_ng_image_check)
        storage_form.addRow("保存 JSON", self.save_json_record_check)
        storage_form.addRow("保存 CSV", self.save_csv_summary_check)
        storage_form.addRow("配方子目录", self.recipe_subdir_mode_combo)
        storage_form.addRow("日期子目录", self.date_subdir_mode_combo)
        storage_form.addRow("保留天数", self.retention_days_spin)

        runtime_group = QGroupBox("运行参数")
        runtime_form = QFormLayout(runtime_group)
        runtime_form.setContentsMargins(14, 16, 14, 12)
        runtime_form.setHorizontalSpacing(10)
        runtime_form.setVerticalSpacing(8)
        runtime_form.addRow("目标节拍 ms", self.target_cycle_spin)
        runtime_form.addRow("检测超时 ms", self.detection_timeout_spin)
        runtime_form.addRow("采图重试次数", self.retry_capture_spin)
        runtime_form.addRow("允许手动测试", self.allow_manual_test_check)

        content_row = QHBoxLayout()
        content_row.setSpacing(10)
        content_row.addWidget(storage_group, 1)
        content_row.addWidget(runtime_group, 1)

        layout.addWidget(intro_label)
        layout.addLayout(content_row)
        layout.addStretch(1)
        return page

    def _bind_events(self) -> None:
        self.button_box.accepted.connect(self._save)
        self.button_box.rejected.connect(self.reject)
        self.trigger_mode_combo.currentTextChanged.connect(self._update_trigger_mode_ui)
        self.template_combo.currentIndexChanged.connect(self._on_template_changed)
        self.capture_template_button.clicked.connect(self._capture_template_image)
        self.reload_template_button.clicked.connect(self._reload_template_image)
        self.add_roi_button.clicked.connect(self._add_roi_row)
        self.remove_roi_button.clicked.connect(self._remove_roi_row)
        self.configure_binary_button.clicked.connect(self._configure_binary_ratio)
        self.configure_ai_button.clicked.connect(self._configure_ai_classifier)
        self.roi_table.itemSelectionChanged.connect(self._on_roi_table_selection_changed)
        self.template_canvas.roi_rects_changed.connect(self._on_canvas_roi_rects_changed)
        self.template_canvas.roi_selected.connect(self._on_canvas_roi_selected)

    def _update_roi_action_state(self) -> None:
        has_selection = self.roi_table.currentRow() >= 0
        self.remove_roi_button.setEnabled(has_selection)
        self.configure_binary_button.setEnabled(has_selection)
        self.configure_ai_button.setEnabled(has_selection)

    def _load_document(self) -> None:
        recipe = self._document.recipe
        self.header_recipe_label.setText(recipe.name or "未命名配方")
        self.recipe_id_edit.setText(recipe.id)
        self.recipe_code_edit.setText(recipe.code)
        self.recipe_name_edit.setText(recipe.name)
        self.product_name_edit.setText(recipe.product_name)
        self.product_model_edit.setText(recipe.product_model)
        self.station_id_edit.setText(recipe.station_id)
        self.camera_id_edit.setText(recipe.camera_id)
        self.recipe_enabled_check.setChecked(recipe.enabled)
        self.trigger_mode_combo.setCurrentText(recipe.trigger_mode)
        self.template_match_mode_combo.setCurrentText(recipe.template_match_mode)
        self.description_edit.setPlainText(recipe.description)

        self.decision_mode_combo.setCurrentText(recipe.decision_policy.mode)
        self.min_pass_count_spin.setValue(recipe.decision_policy.min_pass_count or 0)
        self.allow_disabled_roi_check.setChecked(recipe.decision_policy.allow_disabled_roi)
        self.final_ng_any_fail_check.setChecked(recipe.decision_policy.final_ng_on_any_fail)

        self.grayscale_check.setChecked(recipe.preprocess.grayscale)
        self.denoise_check.setChecked(recipe.preprocess.denoise_enabled)
        self.normalize_check.setChecked(recipe.preprocess.normalize_enabled)
        self.denoise_method_combo.setCurrentText(recipe.preprocess.denoise_method)
        self.resize_mode_combo.setCurrentText(recipe.preprocess.resize_mode)
        self.blur_kernel_spin.setValue(recipe.preprocess.blur_kernel)

        self.plc_enabled_check.setChecked(recipe.plc.enabled)
        self.plc_trigger_source_combo.setCurrentText(recipe.plc.trigger_source)
        self.plc_protocol_edit.setText(recipe.plc.protocol)
        self.plc_timeout_spin.setValue(recipe.plc.timeout_ms)
        self.ng_output_enabled_check.setChecked(recipe.plc.ng_output.enabled)
        self.ng_signal_name_edit.setText(recipe.plc.ng_output.signal_name)
        self.ng_channel_edit.setText(recipe.plc.ng_output.channel)
        self.ng_pulse_spin.setValue(recipe.plc.ng_output.pulse_ms)
        self.ng_delay_spin.setValue(recipe.plc.ng_output.delay_ms)
        self.ng_reset_mode_combo.setCurrentText(recipe.plc.ng_output.reset_mode)
        self._update_trigger_mode_ui(recipe.trigger_mode)

        self.storage_root_dir_edit.setText(recipe.storage.root_dir)
        self.save_raw_image_check.setChecked(recipe.storage.save_raw_image)
        self.save_result_image_check.setChecked(recipe.storage.save_result_image)
        self.save_only_ng_image_check.setChecked(recipe.storage.save_only_ng_image)
        self.save_json_record_check.setChecked(recipe.storage.save_json_record)
        self.save_csv_summary_check.setChecked(recipe.storage.save_csv_summary)
        self.recipe_subdir_mode_combo.setCurrentText(recipe.storage.recipe_subdir_mode)
        self.date_subdir_mode_combo.setCurrentText(recipe.storage.date_subdir_mode)
        self.retention_days_spin.setValue(recipe.storage.max_retention_days)

        self.target_cycle_spin.setValue(recipe.runtime.target_cycle_ms)
        self.detection_timeout_spin.setValue(recipe.runtime.detection_timeout_ms)
        self.retry_capture_spin.setValue(recipe.runtime.retry_on_capture_fail)
        self.allow_manual_test_check.setChecked(recipe.runtime.allow_manual_test)

        self.template_combo.blockSignals(True)
        self.template_combo.clear()
        for index, template in enumerate(recipe.templates):
            self.template_combo.addItem(template.name or f"模板 {index + 1}", index)
        if recipe.templates:
            self._active_template_index = 0
            self.template_combo.setCurrentIndex(0)
            self._load_template(0)
        self.template_combo.blockSignals(False)

    def _on_template_changed(self, index: int) -> None:
        if index < 0:
            return
        self._sync_template_from_form(self._active_template_index)
        self._active_template_index = index
        self._load_template(index)

    def _load_template(self, index: int) -> None:
        template = self._document.recipe.templates[index]
        self.template_code_edit.setText(template.code)
        self.template_name_edit.setText(template.name)
        self.template_enabled_check.setChecked(template.enabled)
        self.template_default_check.setChecked(template.is_default)
        self.template_image_path_edit.setText(template.image_path)
        self.template_width_spin.setValue(template.image_width)
        self.template_height_spin.setValue(template.image_height)
        self.template_description_edit.setPlainText(template.description)
        self._load_roi_table(template)
        self._load_template_image(index)
        self._sync_canvas_from_roi_table(select_row=-1)

    def _load_roi_table(self, template: TemplateConfig) -> None:
        self.roi_table.setRowCount(0)
        for roi in template.roi_list:
            self._append_roi_row(roi)

    def _append_roi_row(self, roi: RoiConfig) -> None:
        row = self.roi_table.rowCount()
        self.roi_table.insertRow(row)

        enabled_item = QTableWidgetItem()
        enabled_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable)
        enabled_item.setCheckState(Qt.Checked if roi.enabled else Qt.Unchecked)
        self.roi_table.setItem(row, 0, enabled_item)
        self.roi_table.setItem(row, 1, self._aligned_table_item(roi.name))
        self.roi_table.setItem(row, 2, self._aligned_table_item(f"{roi.threshold:.3f}"))
        self._set_algorithm_cell(row, roi.algorithm)
        self._set_params_item(row, roi.algorithm, roi.algorithm_params)
        self.roi_table.setItem(row, 5, self._aligned_table_item(roi.description))

    def _add_roi_row(self) -> None:
        QMessageBox.information(self, "手动框选 ROI", "请直接在模板图上按住鼠标左键拖拽，框选新的检测区域。")

    def _remove_roi_row(self) -> None:
        row = self.roi_table.currentRow()
        if row >= 0:
            self.template_canvas.set_selected_roi_index(row)
            self.template_canvas.remove_selected_roi()
            if row < self.roi_table.rowCount():
                self.roi_table.removeRow(row)
            self._sync_canvas_from_roi_table(select_row=-1)

    def _configure_binary_ratio(self) -> None:
        row = self.roi_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "二值化设置", "请先在 ROI 列表中选中一个 ROI。")
            return

        image = self.template_canvas.get_image_array()
        if image is None:
            QMessageBox.information(self, "二值化设置", "请先加载或拍摄模板图。")
            return

        roi_preview_list = self._collect_roi_table_from_document_preview()
        if row >= len(roi_preview_list):
            QMessageBox.warning(self, "二值化设置", "当前 ROI 数据无效，请重新选择。")
            return

        roi = roi_preview_list[row]
        roi_image = self._crop_roi_image(image, roi)
        if roi_image is None:
            QMessageBox.warning(self, "二值化设置", "ROI 超出模板图范围，无法设置二值化参数。")
            return

        dialog = BinaryRatioConfigDialog(
            roi_name=roi.name,
            roi_image=roi_image,
            threshold=roi.threshold,
            algorithm_params=self._params_at(row, fallback=roi.algorithm_params, strict=False),
            parent=self,
        )
        if dialog.exec_() != QDialog.Accepted:
            return

        self._set_algorithm_cell(row, "binary_gray_ratio")
        threshold_text = f"{dialog.result_threshold_min:.3f}-{dialog.result_threshold_max:.3f}"
        self.roi_table.setItem(row, 2, self._aligned_table_item(threshold_text))
        self._set_params_item(row, "binary_gray_ratio", dialog.result_params)
        self.roi_table.selectRow(row)

    def _configure_ai_classifier(self) -> None:
        row = self.roi_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "AI 设置", "请先在 ROI 列表中选中一个 ROI。")
            return

        dialog = AiClassifierConfigDialog(
            algorithm_params=self._params_at(row, fallback={}, strict=False),
            threshold=self._float_at(row, 2, default=0.5),
            parent=self,
        )
        if dialog.exec_() != QDialog.Accepted:
            return

        self._set_algorithm_cell(row, "ai_classifier")
        self.roi_table.setItem(row, 2, self._aligned_table_item(f"{dialog.result_threshold:.3f}"))
        self._set_params_item(row, "ai_classifier", dialog.result_params)
        self.roi_table.selectRow(row)

    def _sync_template_from_form(self, index: int) -> None:
        if index < 0 or index >= len(self._document.recipe.templates):
            return
        template = self._document.recipe.templates[index]
        template.code = self.template_code_edit.text().strip()
        template.name = self.template_name_edit.text().strip()
        template.enabled = self.template_enabled_check.isChecked()
        template.is_default = self.template_default_check.isChecked()
        template.image_path = self.template_image_path_edit.text().strip()
        template.image_width = self.template_width_spin.value()
        template.image_height = self.template_height_spin.value()
        template.description = self.template_description_edit.toPlainText().strip()
        template.roi_list = self._collect_roi_table()

        self.template_combo.setItemText(index, template.name or f"模板 {index + 1}")

    def _collect_roi_table(self) -> list[RoiConfig]:
        existing = self._document.recipe.templates[self._active_template_index].roi_list
        canvas_rects = self.template_canvas.get_roi_rects()
        roi_list: list[RoiConfig] = []
        for row in range(self.roi_table.rowCount()):
            source = existing[row] if row < len(existing) else None
            roi_id = source.id if source is not None else f"roi-{row + 1:03d}"
            rect = canvas_rects[row] if row < len(canvas_rects) else None
            threshold_params = self._params_at(row, fallback=source.algorithm_params if source is not None else None)
            algorithm_key = self._algorithm_at(row)
            threshold_value = self._resolve_row_threshold(
                row=row,
                algorithm=algorithm_key,
                params=threshold_params,
                default=source.threshold if source is not None else 0.9,
            )
            roi_list.append(
                RoiConfig(
                    id=roi_id,
                    index=row + 1,
                    name=self._text_at(row, 1) or f"ROI {row + 1}",
                    enabled=self.roi_table.item(row, 0).checkState() == Qt.Checked,
                    shape=source.shape if source is not None else "rectangle",
                    x=int(rect["x"]) if rect is not None else (source.x if source is not None else 0),
                    y=int(rect["y"]) if rect is not None else (source.y if source is not None else 0),
                    width=max(1, int(rect["width"])) if rect is not None else (source.width if source is not None else 1),
                    height=max(1, int(rect["height"])) if rect is not None else (source.height if source is not None else 1),
                    threshold=threshold_value,
                    algorithm=algorithm_key,
                    algorithm_params=threshold_params,
                    score_weight=source.score_weight if source is not None else 1.0,
                    fail_color=source.fail_color if source is not None else "#ff3b30",
                    pass_color=source.pass_color if source is not None else "#22c55e",
                    description=self._text_at(row, 5),
                    created_at=source.created_at if source is not None else "",
                    updated_at=source.updated_at if source is not None else "",
                )
            )
        return roi_list

    def _text_at(self, row: int, column: int) -> str:
        item = self.roi_table.item(row, column)
        return item.text().strip() if item is not None else ""

    def _algorithm_at(self, row: int) -> str:
        widget = self.roi_table.cellWidget(row, 3)
        if isinstance(widget, QComboBox):
            current_data = widget.currentData()
            if isinstance(current_data, str) and current_data.strip():
                return current_data.strip()
            return self._normalize_algorithm_key(widget.currentText())
        return self._normalize_algorithm_key(self._text_at(row, 3))

    def _set_algorithm_cell(self, row: int, algorithm: str) -> None:
        combo = QComboBox(self.roi_table)
        combo.setObjectName("RoiAlgorithmSelector")
        for algorithm_key in self.ROI_ALGORITHM_OPTIONS:
            combo.addItem(self.ROI_ALGORITHM_LABELS.get(algorithm_key, algorithm_key), algorithm_key)
            combo.setItemData(combo.count() - 1, Qt.AlignCenter, Qt.TextAlignmentRole)
        selected_algorithm = self._normalize_algorithm_key(algorithm)
        combo.setCurrentIndex(max(0, combo.findData(selected_algorithm)))
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.NoInsert)
        combo.lineEdit().setReadOnly(True)
        combo.lineEdit().setFrame(False)
        combo.lineEdit().setAlignment(Qt.AlignCenter)
        combo.lineEdit().setStyleSheet("background: transparent; border: none; padding: 0;")
        combo.currentTextChanged.connect(lambda _text, current_row=row: self._on_algorithm_changed(current_row))
        self.roi_table.setCellWidget(row, 3, combo)

    def _normalize_algorithm_key(self, algorithm_text: str) -> str:
        normalized = (algorithm_text or "").strip().lower()
        if normalized in self.ROI_ALGORITHM_OPTIONS:
            return normalized
        for algorithm_key, label in self.ROI_ALGORITHM_LABELS.items():
            if algorithm_text.strip() == label:
                return algorithm_key
        return self.ROI_ALGORITHM_OPTIONS[0]

    def _algorithm_label(self, algorithm_text: str) -> str:
        return self.ROI_ALGORITHM_LABELS.get(self._normalize_algorithm_key(algorithm_text), algorithm_text or "未设置")

    def _params_text_from_dict(self, params: dict) -> str:
        if not params:
            return "未设置"
        gray_min = params.get("gray_min", 40)
        gray_max = params.get("gray_max", 160)
        invert = "是" if params.get("invert", False) else "否"
        min_area = params.get("min_area", 0)
        threshold_min = float(params.get("threshold_min", 0.0))
        threshold_max = float(params.get("threshold_max", 1.0))
        return (
            f"灰度范围 {gray_min}-{gray_max} / 面积区间 {threshold_min:.3f}-{threshold_max:.3f} / "
            f"反相 {invert} / 最小面积 {min_area}"
        )

    def _ai_params_text_from_dict(self, params: dict) -> str:
        if not params:
            return "未设置"
        model_name = str(params.get("model_name") or Path(str(params.get("model_path", ""))).stem or "未命名模型")
        model_version = str(params.get("model_version") or "-")
        threshold = params.get("score_threshold", 0.5)
        size = f"{params.get('input_width', 224)}x{params.get('input_height', 224)}"
        parallel_algorithm = str(params.get("parallel_algorithm") or "").strip()
        if params.get("parallel_enabled") and parallel_algorithm:
            return (
                f"模型 {model_name} / 版本 {model_version} / 置信阈值 {threshold} / "
                f"输入尺寸 {size} / 并行对照 {self._algorithm_label(parallel_algorithm)}"
            )
        return f"模型 {model_name} / 版本 {model_version} / 置信阈值 {threshold} / 输入尺寸 {size}"

    def _set_params_item(self, row: int, algorithm: str, params: dict | None) -> None:
        params_dict = dict(params or {})
        if algorithm == "binary_gray_ratio":
            text = self._params_text_from_dict(params_dict)
        elif algorithm == "ai_classifier":
            text = self._ai_params_text_from_dict(params_dict)
        elif algorithm == "ssim":
            text = "结构相似度判定 / 无附加参数"
        else:
            text = "未设置"
        item = QTableWidgetItem(text)
        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        item.setData(Qt.UserRole, params_dict)
        self.roi_table.setItem(row, 4, item)

    def _aligned_table_item(self, text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignCenter)
        return item

    def _on_algorithm_changed(self, row: int) -> None:
        if row < 0 or row >= self.roi_table.rowCount():
            return
        algorithm = self._algorithm_at(row)
        existing_params = self._params_at(row, fallback={}, strict=False)
        self._set_params_item(row, algorithm, existing_params if algorithm in {"binary_gray_ratio", "ai_classifier"} else {})
        if self.roi_table.currentRow() == row:
            self._update_roi_action_state()

    def _params_at(self, row: int, fallback=None, strict: bool = True) -> dict:
        item = self.roi_table.item(row, 4)
        if item is not None:
            raw_data = item.data(Qt.UserRole)
            if isinstance(raw_data, dict):
                return dict(raw_data)

        raw_text = self._text_at(row, 4)
        if not raw_text:
            return dict(fallback or {})
        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            if not strict:
                return dict(fallback or {})
            raise ValueError(f"ROI 第 {row + 1} 行参数不是合法 JSON: {exc.msg}") from exc
        if not isinstance(parsed, dict):
            if not strict:
                return dict(fallback or {})
            raise ValueError(f"ROI 第 {row + 1} 行参数必须是 JSON 对象")
        return parsed
    def _int_at(self, row: int, column: int, default: int = 0) -> int:
        text = self._text_at(row, column)
        try:
            return int(text)
        except ValueError:
            return default

    def _float_at(self, row: int, column: int, default: float = 0.0) -> float:
        text = self._text_at(row, column)
        try:
            return float(text)
        except ValueError:
            return default

    def _resolve_row_threshold(self, row: int, algorithm: str, params: dict, default: float) -> float:
        if algorithm == "binary_gray_ratio":
            return float(params.get("threshold_min", default))
        return self._float_at(row, 2, default=default)

    def _update_trigger_mode_ui(self, trigger_mode: str) -> None:
        io_mode = (trigger_mode or "").strip() == "plc_external"
        if io_mode:
            self.tabs.setTabText(2, "检测与IO")
            self.strategy_intro_label.setText(
                "这一页决定检测判定规则与相机 IO 联动方式。当前配方使用外部硬件触发：Line0 负责采图触发，Line1 可用于 NG 输出。"
            )
            self.plc_group.setTitle("相机 IO 与 NG 输出")
            self.plc_enabled_label.setText("启用 IO 联动")
            self.plc_enabled_check.setText("启用相机 IO")
            self.plc_trigger_source_label.setText("触发来源")
            self.plc_protocol_label.setText("通信协议")
            self.plc_timeout_label.setText("等待超时 ms")
            self.ng_output_enabled_label.setText("启用 NG 输出")
            self.ng_signal_name_label.setText("输出说明")
            self.ng_channel_label.setText("相机输出线")
            self.plc_trigger_source_combo.setEnabled(False)
            self.plc_protocol_edit.setEnabled(False)
            self.plc_timeout_spin.setEnabled(False)
            self.plc_trigger_source_combo.setToolTip("相机 IO 模式下由 Line0 直接触发采图，此项不参与运行链路。")
            self.plc_protocol_edit.setToolTip("相机 IO 模式下不走网口协议，此项仅为兼容旧配方保留。")
            self.plc_timeout_spin.setToolTip("实际等待时间由相机外触发轮询控制，此项仅为兼容旧配方保留。")
            self.ng_channel_edit.setPlaceholderText("Line1")
            self.ng_signal_name_edit.setPlaceholderText("例如：NG回传PLC")
            if not self.ng_channel_edit.text().strip():
                self.ng_channel_edit.setText("Line1")
            if not self.ng_signal_name_edit.text().strip():
                self.ng_signal_name_edit.setText("camera_io_ng")
            return

        self.tabs.setTabText(2, "检测与 PLC")
        self.strategy_intro_label.setText("这一页决定检测判定规则和 PLC 联动方式，优先确保阈值策略与现场节拍要求一致。")
        self.plc_group.setTitle("PLC 配置")
        self.plc_enabled_label.setText("启用 PLC")
        self.plc_enabled_check.setText("启用 PLC")
        self.plc_trigger_source_label.setText("触发来源")
        self.plc_protocol_label.setText("协议")
        self.plc_timeout_label.setText("超时 ms")
        self.ng_output_enabled_label.setText("启用 NG 输出")
        self.ng_signal_name_label.setText("信号名")
        self.ng_channel_label.setText("输出通道")
        self.plc_trigger_source_combo.setEnabled(True)
        self.plc_protocol_edit.setEnabled(True)
        self.plc_timeout_spin.setEnabled(True)
        self.plc_trigger_source_combo.setToolTip("")
        self.plc_protocol_edit.setToolTip("")
        self.plc_timeout_spin.setToolTip("")
        self.ng_channel_edit.setPlaceholderText("例如：Y0 / M100")
        self.ng_signal_name_edit.setPlaceholderText("例如：ng_alarm")

    def _save(self) -> None:
        if not self.recipe_id_edit.text().strip() or not self.recipe_name_edit.text().strip():
            QMessageBox.warning(self, "保存失败", "配方 ID 和配方名称不能为空")
            return

        try:
            self._sync_template_from_form(self._active_template_index)
            self._apply_form_to_document()
        except ValueError as exc:
            QMessageBox.warning(self, "保存失败", str(exc))
            return

        try:
            self._recipe_controller.save_recipe(self._document)
        except Exception as exc:
            QMessageBox.critical(self, "保存失败", str(exc))
            return
        self.accept()

    def _apply_form_to_document(self) -> None:
        recipe = self._document.recipe
        recipe.id = self.recipe_id_edit.text().strip()
        recipe.code = self.recipe_code_edit.text().strip()
        recipe.name = self.recipe_name_edit.text().strip()
        recipe.product_name = self.product_name_edit.text().strip()
        recipe.product_model = self.product_model_edit.text().strip()
        recipe.station_id = self.station_id_edit.text().strip()
        recipe.camera_id = self.camera_id_edit.text().strip()
        recipe.enabled = self.recipe_enabled_check.isChecked()
        recipe.trigger_mode = self.trigger_mode_combo.currentText()
        recipe.template_match_mode = self.template_match_mode_combo.currentText()
        recipe.description = self.description_edit.toPlainText().strip()

        recipe.decision_policy.mode = self.decision_mode_combo.currentText()
        recipe.decision_policy.min_pass_count = self.min_pass_count_spin.value() or None
        recipe.decision_policy.allow_disabled_roi = self.allow_disabled_roi_check.isChecked()
        recipe.decision_policy.final_ng_on_any_fail = self.final_ng_any_fail_check.isChecked()

        recipe.preprocess.grayscale = self.grayscale_check.isChecked()
        recipe.preprocess.denoise_enabled = self.denoise_check.isChecked()
        recipe.preprocess.normalize_enabled = self.normalize_check.isChecked()
        recipe.preprocess.denoise_method = self.denoise_method_combo.currentText()
        recipe.preprocess.resize_mode = self.resize_mode_combo.currentText()
        recipe.preprocess.blur_kernel = self.blur_kernel_spin.value()

        recipe.plc.enabled = self.plc_enabled_check.isChecked()
        recipe.plc.trigger_source = self.plc_trigger_source_combo.currentText()
        recipe.plc.protocol = self.plc_protocol_edit.text().strip()
        recipe.plc.timeout_ms = self.plc_timeout_spin.value()
        recipe.plc.ng_output.enabled = self.ng_output_enabled_check.isChecked()
        recipe.plc.ng_output.signal_name = self.ng_signal_name_edit.text().strip()
        recipe.plc.ng_output.channel = self.ng_channel_edit.text().strip()
        recipe.plc.ng_output.pulse_ms = self.ng_pulse_spin.value()
        recipe.plc.ng_output.delay_ms = self.ng_delay_spin.value()
        recipe.plc.ng_output.reset_mode = self.ng_reset_mode_combo.currentText()

        recipe.storage.root_dir = self.storage_root_dir_edit.text().strip()
        recipe.storage.save_raw_image = self.save_raw_image_check.isChecked()
        recipe.storage.save_result_image = self.save_result_image_check.isChecked()
        recipe.storage.save_only_ng_image = self.save_only_ng_image_check.isChecked()
        recipe.storage.save_json_record = self.save_json_record_check.isChecked()
        recipe.storage.save_csv_summary = self.save_csv_summary_check.isChecked()
        recipe.storage.recipe_subdir_mode = self.recipe_subdir_mode_combo.currentText()
        recipe.storage.date_subdir_mode = self.date_subdir_mode_combo.currentText()
        recipe.storage.max_retention_days = self.retention_days_spin.value()

        recipe.runtime.target_cycle_ms = self.target_cycle_spin.value()
        recipe.runtime.detection_timeout_ms = self.detection_timeout_spin.value()
        recipe.runtime.retry_on_capture_fail = self.retry_capture_spin.value()
        recipe.runtime.allow_manual_test = self.allow_manual_test_check.isChecked()

        timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
        recipe.updated_at = timestamp
        for template in recipe.templates:
            template.updated_at = timestamp
            for roi in template.roi_list:
                roi.updated_at = timestamp

        self._persist_template_images()

    def _capture_template_image(self) -> None:
        try:
            capture = self._camera_controller.capture_manual_frame(preferred_device_index=0)
        except Exception as exc:
            QMessageBox.critical(self, "拍摄失败", str(exc))
            return

        image = capture.frame.image
        self._template_images[self._active_template_index] = image.copy()
        self.template_canvas.set_image_array(image)
        self.template_width_spin.setValue(capture.frame.width)
        self.template_height_spin.setValue(capture.frame.height)
        self.template_canvas.set_roi_rects([])
        self.roi_table.setRowCount(0)
        if not self.template_image_path_edit.text().strip():
            self.template_image_path_edit.setText(self._default_template_image_path(self._active_template_index))

    def _reload_template_image(self) -> None:
        self._load_template_image(self._active_template_index, force_reload=True)
        self._sync_canvas_from_roi_table(select_row=self.roi_table.currentRow())

    def _load_template_image(self, index: int, force_reload: bool = False) -> None:
        if not force_reload and index in self._template_images and self._template_images[index] is not None:
            self.template_canvas.set_image_array(self._template_images[index])
            return

        template = self._document.recipe.templates[index]
        image_path_text = template.image_path.strip()
        if not image_path_text:
            self._template_images[index] = None
            self.template_canvas.clear_image()
            return

        image_path = Path(image_path_text)
        if not image_path.is_absolute():
            image_path = self._project_root() / image_path
        if not image_path.exists():
            self._template_images[index] = None
            self.template_canvas.clear_image()
            return

        image = self._read_image(image_path)
        self._template_images[index] = image
        self.template_canvas.set_image_array(image)

    def _read_image(self, image_path: Path) -> np.ndarray:
        if cv2 is not None:
            image = cv2.imread(str(image_path), cv2.IMREAD_UNCHANGED)
            if image is not None:
                return image

        qimage = QImage(str(image_path))
        if qimage.isNull():
            raise RuntimeError(f"模板图无法读取: {image_path}")
        if qimage.format() != QImage.Format_Grayscale8:
            qimage = qimage.convertToFormat(QImage.Format_RGB888)
            width = qimage.width()
            height = qimage.height()
            buffer = qimage.bits()
            buffer.setsize(height * qimage.bytesPerLine())
            return np.frombuffer(buffer, dtype=np.uint8).reshape(height, qimage.bytesPerLine() // 3, 3)[:, :width, :].copy()[:, :, ::-1]

        width = qimage.width()
        height = qimage.height()
        buffer = qimage.bits()
        buffer.setsize(height * qimage.bytesPerLine())
        return np.frombuffer(buffer, dtype=np.uint8).reshape(height, qimage.bytesPerLine())[:, :width].copy()

    def _persist_template_images(self) -> None:
        for index, image in self._template_images.items():
            if image is None or index >= len(self._document.recipe.templates):
                continue
            template = self._document.recipe.templates[index]
            image_path_text = template.image_path.strip() or self._default_template_image_path(index)
            template.image_path = image_path_text
            image_path = Path(image_path_text)
            if not image_path.is_absolute():
                image_path = self._project_root() / image_path
            image_path.parent.mkdir(parents=True, exist_ok=True)
            self._write_image(image_path, image)
            template.image_width = image.shape[1]
            template.image_height = image.shape[0]

    def _write_image(self, image_path: Path, image: np.ndarray) -> None:
        if cv2 is not None:
            if cv2.imwrite(str(image_path), image):
                return

        array = np.ascontiguousarray(image)
        if array.ndim == 2:
            qimage = QImage(array.data, array.shape[1], array.shape[0], array.strides[0], QImage.Format_Grayscale8).copy()
        else:
            rgb = array[:, :, ::-1].copy()
            qimage = QImage(rgb.data, rgb.shape[1], rgb.shape[0], rgb.strides[0], QImage.Format_RGB888).copy()
        if not qimage.save(str(image_path)):
            raise RuntimeError(f"模板图保存失败: {image_path}")

    def _default_template_image_path(self, index: int) -> str:
        recipe_id = self.recipe_id_edit.text().strip() or self._document.recipe.id
        return str((Path("data") / "templates" / recipe_id / f"template_{index + 1}.jpg").as_posix())

    def _project_root(self) -> Path:
        return Path(__file__).resolve().parents[1]

    def _crop_roi_image(self, image: np.ndarray, roi: RoiConfig):
        height, width = image.shape[:2]
        if roi.x < 0 or roi.y < 0 or roi.width <= 0 or roi.height <= 0:
            return None
        if roi.x + roi.width > width or roi.y + roi.height > height:
            return None
        return image[roi.y : roi.y + roi.height, roi.x : roi.x + roi.width].copy()

    def _on_canvas_roi_rects_changed(self, roi_rects) -> None:
        current_rows = self.roi_table.rowCount()
        if len(roi_rects) > current_rows:
            for row in range(current_rows, len(roi_rects)):
                roi = RoiConfig(
                    id=f"roi-{row + 1:03d}",
                    index=row + 1,
                    name=f"ROI {row + 1}",
                    enabled=True,
                    shape="rectangle",
                    x=int(roi_rects[row]["x"]),
                    y=int(roi_rects[row]["y"]),
                    width=max(1, int(roi_rects[row]["width"])),
                    height=max(1, int(roi_rects[row]["height"])),
                    threshold=0.15,
                    algorithm="binary_gray_ratio",
                    algorithm_params={},
                    description="",
                )
                self._append_roi_row(roi)
        elif len(roi_rects) < current_rows:
            while self.roi_table.rowCount() > len(roi_rects):
                self.roi_table.removeRow(self.roi_table.rowCount() - 1)

        for row in range(min(self.roi_table.rowCount(), len(roi_rects))):
            if not self._text_at(row, 1):
                self.roi_table.setItem(row, 1, QTableWidgetItem(f"ROI {row + 1}"))

    def _on_canvas_roi_selected(self, index: int) -> None:
        if 0 <= index < self.roi_table.rowCount():
            self.roi_table.selectRow(index)
        self._update_roi_action_state()

    def _on_roi_table_selection_changed(self) -> None:
        row = self.roi_table.currentRow()
        self.template_canvas.set_selected_roi_index(row)
        self._update_roi_action_state()

    def _sync_canvas_from_roi_table(self, select_row: int = -1) -> None:
        roi_rects = []
        for roi in self._collect_roi_table_from_document_preview():
            roi_rects.append(
                {
                    "name": roi.name,
                    "x": roi.x,
                    "y": roi.y,
                    "width": roi.width,
                    "height": roi.height,
                    "color": roi.pass_color if roi.enabled else "#9ca3af",
                }
            )
        self.template_canvas.set_roi_rects(roi_rects)
        self.template_canvas.set_selected_roi_index(select_row)

    def _collect_roi_table_from_document_preview(self) -> list[RoiConfig]:
        existing = self._document.recipe.templates[self._active_template_index].roi_list
        roi_list: list[RoiConfig] = []
        canvas_rects = self.template_canvas.get_roi_rects()
        for row in range(self.roi_table.rowCount()):
            source = existing[row] if row < len(existing) else None
            canvas_rect = canvas_rects[row] if row < len(canvas_rects) else None
            roi_list.append(
                RoiConfig(
                    id=source.id if source is not None else f"roi-{row + 1:03d}",
                    index=row + 1,
                    name=self._text_at(row, 1) or f"ROI {row + 1}",
                    enabled=self.roi_table.item(row, 0).checkState() == Qt.Checked,
                    shape="rectangle",
                    x=int(canvas_rect["x"]) if canvas_rect is not None else (source.x if source is not None else 0),
                    y=int(canvas_rect["y"]) if canvas_rect is not None else (source.y if source is not None else 0),
                    width=max(1, int(canvas_rect["width"])) if canvas_rect is not None else (source.width if source is not None else 1),
                    height=max(1, int(canvas_rect["height"])) if canvas_rect is not None else (source.height if source is not None else 1),
                    threshold=self._float_at(row, 2, default=0.9),
                    algorithm=self._algorithm_at(row),
                    algorithm_params=self._params_at(
                        row,
                        fallback=source.algorithm_params if source is not None else None,
                        strict=False,
                    ),
                    score_weight=source.score_weight if source is not None else 1.0,
                    fail_color=source.fail_color if source is not None else "#ff3b30",
                    pass_color=source.pass_color if source is not None else "#22c55e",
                    description=self._text_at(row, 5),
                    created_at=source.created_at if source is not None else "",
                    updated_at=source.updated_at if source is not None else "",
                )
            )
        return roi_list
