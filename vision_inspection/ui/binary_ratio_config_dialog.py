from __future__ import annotations

from typing import Any, Dict

import numpy as np
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class BinaryRatioConfigDialog(QDialog):
    PARAMETER_TEMPLATES = {
        "通用默认": {"gray_min": 40, "gray_max": 160, "invert": False, "min_area": 0, "threshold_min": 0.15, "threshold_max": 0.55},
        "灰色垫片": {"gray_min": 70, "gray_max": 150, "invert": False, "min_area": 30, "threshold_min": 0.08, "threshold_max": 0.30},
        "暗色涂胶": {"gray_min": 0, "gray_max": 95, "invert": False, "min_area": 20, "threshold_min": 0.05, "threshold_max": 0.25},
        "高对比窄范围": {"gray_min": 90, "gray_max": 135, "invert": False, "min_area": 15, "threshold_min": 0.06, "threshold_max": 0.18},
    }

    def __init__(
        self,
        roi_name: str,
        roi_image: np.ndarray,
        threshold: float,
        algorithm_params: Dict[str, Any] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._roi_name = roi_name
        self._roi_image = roi_image.copy()
        self._algorithm_params = dict(algorithm_params or {})

        self.setWindowTitle(f"二值化参数设置 - {roi_name}")
        self.resize(1080, 760)

        self._build_widgets(threshold)
        self._build_layout()
        self._bind_events()
        self._load_params()
        self._update_preview()

    @property
    def result_threshold_min(self) -> float:
        threshold_min, _threshold_max = self._current_threshold_range()
        return threshold_min

    @property
    def result_threshold_max(self) -> float:
        _threshold_min, threshold_max = self._current_threshold_range()
        return threshold_max

    @property
    def result_params(self) -> Dict[str, Any]:
        gray_min, gray_max = self._current_gray_range()
        threshold_min, threshold_max = self._current_threshold_range()
        return {
            "gray_min": gray_min,
            "gray_max": gray_max,
            "invert": bool(self.invert_check.isChecked()),
            "min_area": int(self.min_area_spin.value()),
            "threshold_min": threshold_min,
            "threshold_max": threshold_max,
        }

    def _build_widgets(self, threshold: float) -> None:
        self.original_label = QLabel()
        self.original_label.setAlignment(Qt.AlignCenter)
        self.original_label.setMinimumSize(360, 280)
        self.original_label.setStyleSheet("background:#111827; color:#d1d5db; border:1px solid #374151;")

        self.binary_label = QLabel()
        self.binary_label.setAlignment(Qt.AlignCenter)
        self.binary_label.setMinimumSize(360, 280)
        self.binary_label.setStyleSheet("background:#111827; color:#d1d5db; border:1px solid #374151;")

        self.gray_min_spin = QSpinBox()
        self.gray_min_spin.setRange(0, 255)
        self.gray_max_spin = QSpinBox()
        self.gray_max_spin.setRange(0, 255)
        self.min_area_spin = QSpinBox()
        self.min_area_spin.setRange(0, 1000000)
        self.invert_check = QCheckBox("反相")
        threshold_min, threshold_max = self._resolve_threshold_range(threshold)
        self.threshold_min_spin = QDoubleSpinBox()
        self.threshold_min_spin.setRange(0.0, 1.0)
        self.threshold_min_spin.setDecimals(4)
        self.threshold_min_spin.setSingleStep(0.01)
        self.threshold_min_spin.setValue(threshold_min)
        self.threshold_max_spin = QDoubleSpinBox()
        self.threshold_max_spin.setRange(0.0, 1.0)
        self.threshold_max_spin.setDecimals(4)
        self.threshold_max_spin.setSingleStep(0.01)
        self.threshold_max_spin.setValue(threshold_max)

        self.template_combo = QComboBox()
        self.template_combo.addItems(list(self.PARAMETER_TEMPLATES.keys()))
        self.apply_template_button = QPushButton("套用模板")

        self.gray_min_hint = QLabel("保留目标区域的最低灰度值。值越大，越偏向中亮区域。")
        self.gray_max_hint = QLabel("保留目标区域的最高灰度值。值越小，越容易滤掉亮背景。")
        self.min_area_hint = QLabel("过滤零碎噪点。小于该面积的白色连通块会被丢弃。")
        self.invert_hint = QLabel("若目标在预览里应该是黑色而不是白色，勾选后可翻转目标与背景。")
        self.threshold_hint = QLabel("当白色目标面积比例落在设定区间内时，ROI 判定为通过。")
        for hint in [
            self.gray_min_hint,
            self.gray_max_hint,
            self.min_area_hint,
            self.invert_hint,
            self.threshold_hint,
        ]:
            hint.setWordWrap(True)
            hint.setStyleSheet("color:#6b7280; font-size:12px;")

        self.template_hint = QLabel(
            "模板作用：先给出一组可用起点，再根据右侧二值化预览和实时面积比例微调。"
        )
        self.template_hint.setWordWrap(True)
        self.template_hint.setStyleSheet("color:#6b7280; font-size:12px;")

        self.score_label = QLabel("面积比例: -")
        self.score_label.setStyleSheet("font-size:16px; font-weight:bold;")
        self.guide_label = QLabel(
            "设置流程:\n"
            "1. 调整灰度下限和上限，让目标区域尽量变成白色。\n"
            "2. 若检测对象应该是黑区，则勾选反相。\n"
            "3. 用最小面积过滤掉零碎噪点。\n"
            "4. 观察实时面积比例，再设置通过区间的下限和上限。"
        )
        self.guide_label.setWordWrap(True)

        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)

    def _build_layout(self) -> None:
        root_layout = QVBoxLayout(self)

        preview_group = QGroupBox("ROI 预览")
        preview_layout = QGridLayout(preview_group)
        preview_layout.addWidget(QLabel("原图 ROI"), 0, 0)
        preview_layout.addWidget(QLabel("二值化结果"), 0, 1)
        preview_layout.addWidget(self.original_label, 1, 0)
        preview_layout.addWidget(self.binary_label, 1, 1)

        config_group = QGroupBox("参数设置")
        config_form = QFormLayout(config_group)
        template_row = QWidget()
        template_row_layout = QGridLayout(template_row)
        template_row_layout.setContentsMargins(0, 0, 0, 0)
        template_row_layout.addWidget(self.template_combo, 0, 0)
        template_row_layout.addWidget(self.apply_template_button, 0, 1)
        config_form.addRow("参数模板", template_row)
        config_form.addRow("模板说明", self.template_hint)
        config_form.addRow("灰度下限", self.gray_min_spin)
        config_form.addRow("下限说明", self.gray_min_hint)
        config_form.addRow("灰度上限", self.gray_max_spin)
        config_form.addRow("上限说明", self.gray_max_hint)
        config_form.addRow("最小连通面积", self.min_area_spin)
        config_form.addRow("面积说明", self.min_area_hint)
        config_form.addRow("反相", self.invert_check)
        config_form.addRow("反相说明", self.invert_hint)
        config_form.addRow("通过下限", self.threshold_min_spin)
        config_form.addRow("通过上限", self.threshold_max_spin)
        config_form.addRow("阈值说明", self.threshold_hint)
        config_form.addRow("实时面积比例", self.score_label)

        guide_group = QGroupBox("设置说明")
        guide_layout = QVBoxLayout(guide_group)
        guide_layout.addWidget(self.guide_label)

        root_layout.addWidget(preview_group, 3)
        root_layout.addWidget(config_group, 2)
        root_layout.addWidget(guide_group, 1)
        root_layout.addWidget(self.button_box)

    def _bind_events(self) -> None:
        self.apply_template_button.clicked.connect(self._apply_selected_template)
        self.gray_min_spin.valueChanged.connect(self._update_preview)
        self.gray_max_spin.valueChanged.connect(self._update_preview)
        self.min_area_spin.valueChanged.connect(self._update_preview)
        self.invert_check.toggled.connect(self._update_preview)
        self.threshold_min_spin.valueChanged.connect(self._update_preview)
        self.threshold_max_spin.valueChanged.connect(self._update_preview)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

    def _load_params(self) -> None:
        self.gray_min_spin.setValue(int(self._algorithm_params.get("gray_min", 40)))
        self.gray_max_spin.setValue(int(self._algorithm_params.get("gray_max", 160)))
        self.invert_check.setChecked(bool(self._algorithm_params.get("invert", False)))
        self.min_area_spin.setValue(int(self._algorithm_params.get("min_area", 0)))

    def _apply_selected_template(self) -> None:
        template_name = self.template_combo.currentText()
        template = self.PARAMETER_TEMPLATES.get(template_name)
        if template is None:
            return

        self.gray_min_spin.setValue(int(template["gray_min"]))
        self.gray_max_spin.setValue(int(template["gray_max"]))
        self.invert_check.setChecked(bool(template["invert"]))
        self.min_area_spin.setValue(int(template["min_area"]))
        self.threshold_min_spin.setValue(float(template["threshold_min"]))
        self.threshold_max_spin.setValue(float(template["threshold_max"]))

    def _resolve_threshold_range(self, fallback_threshold: float) -> tuple[float, float]:
        threshold_min = float(self._algorithm_params.get("threshold_min", fallback_threshold))
        threshold_max = float(self._algorithm_params.get("threshold_max", 1.0))
        threshold_min = max(0.0, min(1.0, threshold_min))
        threshold_max = max(0.0, min(1.0, threshold_max))
        if threshold_max < threshold_min:
            threshold_max = threshold_min
        return threshold_min, threshold_max

    def _current_threshold_range(self) -> tuple[float, float]:
        threshold_min = min(self.threshold_min_spin.value(), self.threshold_max_spin.value())
        threshold_max = max(self.threshold_min_spin.value(), self.threshold_max_spin.value())
        return float(threshold_min), float(threshold_max)

    def _current_gray_range(self) -> tuple[int, int]:
        gray_min = min(self.gray_min_spin.value(), self.gray_max_spin.value())
        gray_max = max(self.gray_min_spin.value(), self.gray_max_spin.value())
        return int(gray_min), int(gray_max)

    def _update_preview(self) -> None:
        gray_image = self._to_grayscale(self._roi_image)
        gray_min, gray_max = self._current_gray_range()
        threshold_min, threshold_max = self._current_threshold_range()

        mask = (gray_image >= gray_min) & (gray_image <= gray_max)
        if self.invert_check.isChecked():
            mask = ~mask

        min_area = max(0, int(self.min_area_spin.value()))
        if min_area > 1:
            mask = self._remove_small_components(mask, min_area)

        ratio = float(np.count_nonzero(mask) / mask.size) if mask.size else 0.0
        passed = threshold_min <= ratio <= threshold_max
        self.score_label.setText(
            f"面积比例: {ratio:.4f} ({np.count_nonzero(mask)} / {mask.size}) / 判定区间: {threshold_min:.4f}-{threshold_max:.4f} / {'通过' if passed else '未通过'}"
        )

        self._set_preview(self.original_label, self._roi_image)
        self._set_preview(self.binary_label, (mask.astype(np.uint8) * 255))

    def _set_preview(self, target: QLabel, image: np.ndarray) -> None:
        pixmap = self._to_pixmap(image)
        if pixmap.isNull():
            target.setText("预览失败")
            return
        target.setPixmap(pixmap.scaled(target.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    @staticmethod
    def _to_grayscale(image: np.ndarray) -> np.ndarray:
        if image.ndim == 2:
            return image.copy()
        return np.mean(image[:, :, :3], axis=2).astype(np.uint8)

    @staticmethod
    def _to_pixmap(image: np.ndarray) -> QPixmap:
        array = np.ascontiguousarray(image)
        if array.ndim == 2:
            qimage = QImage(array.data, array.shape[1], array.shape[0], array.strides[0], QImage.Format_Grayscale8).copy()
            return QPixmap.fromImage(qimage)

        if array.ndim == 3 and array.shape[2] == 3:
            rgb = array[:, :, ::-1].copy()
            qimage = QImage(rgb.data, rgb.shape[1], rgb.shape[0], rgb.strides[0], QImage.Format_RGB888).copy()
            return QPixmap.fromImage(qimage)

        return QPixmap()

    @staticmethod
    def _remove_small_components(mask: np.ndarray, min_area: int) -> np.ndarray:
        height, width = mask.shape
        visited = np.zeros((height, width), dtype=bool)
        filtered = np.zeros((height, width), dtype=bool)
        neighbors = [(-1, 0), (1, 0), (0, -1), (0, 1)]

        for y in range(height):
            for x in range(width):
                if visited[y, x] or not mask[y, x]:
                    continue
                stack = [(y, x)]
                component = []
                visited[y, x] = True
                while stack:
                    cy, cx = stack.pop()
                    component.append((cy, cx))
                    for dy, dx in neighbors:
                        ny = cy + dy
                        nx = cx + dx
                        if 0 <= ny < height and 0 <= nx < width and not visited[ny, nx] and mask[ny, nx]:
                            visited[ny, nx] = True
                            stack.append((ny, nx))
                if len(component) >= min_area:
                    for cy, cx in component:
                        filtered[cy, cx] = True
        return filtered