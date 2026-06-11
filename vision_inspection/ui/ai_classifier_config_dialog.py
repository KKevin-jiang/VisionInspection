from __future__ import annotations

from pathlib import Path

from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)


class AiClassifierConfigDialog(QDialog):
    def __init__(self, algorithm_params: dict | None = None, threshold: float = 0.5, parent=None) -> None:
        super().__init__(parent)
        self._algorithm_params = dict(algorithm_params or {})
        self._result_params = dict(self._algorithm_params)
        self._result_threshold = float(self._algorithm_params.get("score_threshold", threshold))

        self.setWindowTitle("AI 分类设置")
        self.resize(560, 360)
        self._build_ui()
        self._load_values()

    @property
    def result_params(self) -> dict:
        return dict(self._result_params)

    @property
    def result_threshold(self) -> float:
        return self._result_threshold

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setContentsMargins(12, 12, 12, 12)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)

        self.model_path_edit = QLineEdit()
        browse_button = QPushButton("选择模型")
        browse_button.clicked.connect(self._browse_model)
        model_row = QHBoxLayout()
        model_row.addWidget(self.model_path_edit, 1)
        model_row.addWidget(browse_button)

        self.model_name_edit = QLineEdit()
        self.model_version_edit = QLineEdit()
        self.class_names_edit = QLineEdit()
        self.positive_label_edit = QLineEdit()
        self.input_width_spin = QSpinBox()
        self.input_width_spin.setRange(1, 4096)
        self.input_height_spin = QSpinBox()
        self.input_height_spin.setRange(1, 4096)
        self.score_threshold_edit = QLineEdit()
        self.color_mode_combo = QComboBox()
        self.color_mode_combo.addItems(["rgb", "gray"])
        self.normalize_check = QCheckBox("归一化到 0-1")
        self.mean_edit = QLineEdit()
        self.std_edit = QLineEdit()

        form.addRow("模型路径", model_row)
        form.addRow("模型名称", self.model_name_edit)
        form.addRow("模型版本", self.model_version_edit)
        form.addRow("类别列表", self.class_names_edit)
        form.addRow("正样本类别", self.positive_label_edit)
        form.addRow("输入宽度", self.input_width_spin)
        form.addRow("输入高度", self.input_height_spin)
        form.addRow("判定阈值", self.score_threshold_edit)
        form.addRow("颜色模式", self.color_mode_combo)
        form.addRow("归一化", self.normalize_check)
        form.addRow("mean", self.mean_edit)
        form.addRow("std", self.std_edit)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self._accept)
        button_box.rejected.connect(self.reject)

        root_layout.addLayout(form)
        root_layout.addWidget(button_box)

    def _load_values(self) -> None:
        self.model_path_edit.setText(str(self._algorithm_params.get("model_path", "")))
        self.model_name_edit.setText(str(self._algorithm_params.get("model_name", "")))
        self.model_version_edit.setText(str(self._algorithm_params.get("model_version", "")))
        class_names = self._algorithm_params.get("class_names", ["negative", "positive"])
        if isinstance(class_names, list):
            class_names = ", ".join(str(item) for item in class_names)
        self.class_names_edit.setText(str(class_names))
        self.positive_label_edit.setText(str(self._algorithm_params.get("positive_label", "positive")))
        self.input_width_spin.setValue(int(self._algorithm_params.get("input_width", 224)))
        self.input_height_spin.setValue(int(self._algorithm_params.get("input_height", 224)))
        self.score_threshold_edit.setText(str(self._algorithm_params.get("score_threshold", self._result_threshold)))
        self.color_mode_combo.setCurrentText(str(self._algorithm_params.get("color_mode", "rgb")))
        self.normalize_check.setChecked(bool(self._algorithm_params.get("normalize_to_01", True)))
        mean = self._algorithm_params.get("mean", [0.485, 0.456, 0.406])
        std = self._algorithm_params.get("std", [0.229, 0.224, 0.225])
        self.mean_edit.setText(", ".join(str(item) for item in mean))
        self.std_edit.setText(", ".join(str(item) for item in std))

    def _browse_model(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "选择 ONNX 模型", str(Path.cwd()), "ONNX 模型 (*.onnx)")
        if file_path:
            self.model_path_edit.setText(file_path)

    def _accept(self) -> None:
        class_names = [item.strip() for item in self.class_names_edit.text().split(",") if item.strip()]
        if not self.model_path_edit.text().strip():
            self.model_path_edit.setFocus()
            return
        if len(class_names) < 2:
            self.class_names_edit.setFocus()
            return

        self._result_threshold = float(self.score_threshold_edit.text().strip() or "0.5")
        self._result_params = dict(self._algorithm_params)
        self._result_params.update({
            "model_path": self.model_path_edit.text().strip(),
            "model_name": self.model_name_edit.text().strip(),
            "model_version": self.model_version_edit.text().strip(),
            "class_names": class_names,
            "positive_label": self.positive_label_edit.text().strip() or class_names[-1],
            "input_width": self.input_width_spin.value(),
            "input_height": self.input_height_spin.value(),
            "score_threshold": self._result_threshold,
            "color_mode": self.color_mode_combo.currentText(),
            "normalize_to_01": self.normalize_check.isChecked(),
            "mean": [float(item.strip()) for item in self.mean_edit.text().split(",") if item.strip()],
            "std": [float(item.strip()) for item in self.std_edit.text().split(",") if item.strip()],
        })
        self.accept()