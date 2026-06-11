from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from time import perf_counter
from typing import Optional

import numpy as np
from PyQt5.QtGui import QImage

from vision_inspection.domain.models.inspection_result import BoundingBox, InspectionResult, RoiInspectionResult
from vision_inspection.domain.models.recipe import RecipeDocument, RoiConfig, TemplateConfig
from vision_inspection.infrastructure.vision.preprocess import apply_preprocess
from vision_inspection.infrastructure.vision.similarity import compute_ssim_score

try:
    import onnxruntime as ort  # type: ignore[import-not-found]
except ImportError:
    ort = None


class InspectionDetectorError(RuntimeError):
    pass


@dataclass
class AiEvaluationResult:
    score: float
    passed: bool
    message: str
    predicted_label: str = ""
    confidence: float | None = None
    model_name: str = ""
    model_version: str = ""
    inference_ms: float | None = None
    parallel_algorithm: str = ""
    parallel_score: float | None = None
    parallel_passed: bool | None = None
    parallel_message: str = ""
    parallel_predicted_label: str = ""
    parallel_confidence: float | None = None
    parallel_model_name: str = ""
    parallel_model_version: str = ""
    parallel_inference_ms: float | None = None


class InspectionDetector:
    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir
        self._ai_sessions: dict[str, object] = {}
        self._template_image_cache: dict[str, np.ndarray] = {}
        self._template_roi_preprocess_cache: dict[tuple[str, bool, bool, int, bool, int, int, int, int], np.ndarray] = {}

    def inspect(self, recipe_document: RecipeDocument, captured_image: np.ndarray) -> InspectionResult:
        inspect_started_at = perf_counter()
        template = self._select_template(recipe_document)
        template_load_started_at = perf_counter()
        template_image = self._load_template_image(template)
        template_path = self._resolve_template_path(template)
        template_load_ms = (perf_counter() - template_load_started_at) * 1000.0

        preprocess = recipe_document.recipe.preprocess
        roi_results = []
        enabled_scores = []
        ng_found = False
        roi_preprocess_ms = 0.0
        roi_eval_ms = 0.0

        for roi in template.roi_list:
            roi_result, preprocess_ms, eval_ms = self._inspect_single_roi(
                roi=roi,
                captured_image=captured_image,
                template_image=template_image,
                template_path=template_path,
                preprocess=preprocess,
            )
            roi_results.append(roi_result)
            roi_preprocess_ms += preprocess_ms
            roi_eval_ms += eval_ms
            if roi.enabled and roi_result.score is not None:
                enabled_scores.append(roi_result.score)
            if roi.enabled and not roi_result.passed:
                ng_found = True

        overall_score = sum(enabled_scores) / len(enabled_scores) if enabled_scores else None
        overall_result = "NG" if ng_found else "OK"

        return InspectionResult(
            recipe_id=recipe_document.recipe.id,
            recipe_name=recipe_document.recipe.name,
            template_id=template.id,
            template_name=template.name,
            overall_result=overall_result,
            roi_results=roi_results,
            overall_score=overall_score,
            phase_metrics={
                "template_load_ms": template_load_ms,
                "roi_preprocess_ms": roi_preprocess_ms,
                "roi_eval_ms": roi_eval_ms,
                "detect_total_ms": (perf_counter() - inspect_started_at) * 1000.0,
            },
        )

    def _select_template(self, recipe_document: RecipeDocument) -> TemplateConfig:
        templates = [item for item in recipe_document.recipe.templates if item.enabled]
        if not templates:
            raise InspectionDetectorError("当前配方没有启用模板")
        for template in templates:
            if template.is_default:
                return template
        return templates[0]

    def _resolve_template_path(self, template: TemplateConfig) -> Path:
        template_path = Path(template.image_path)
        if template_path.is_absolute():
            return template_path

        project_root = self._data_dir.parent
        candidate_paths = []
        if template_path.parts and template_path.parts[0].lower() == "data":
            candidate_paths.append(project_root / template_path)
        candidate_paths.append(self._data_dir / template_path)

        for candidate_path in candidate_paths:
            if candidate_path.exists():
                return candidate_path

        return candidate_paths[0]

    def _load_template_image(self, template: TemplateConfig) -> np.ndarray:
        template_path = self._resolve_template_path(template)
        if not template_path.exists():
            raise InspectionDetectorError(f"模板文件不存在: {template_path}")

        cache_key = str(template_path.resolve())
        cached = self._template_image_cache.get(cache_key)
        if cached is not None:
            return cached

        image = QImage(str(template_path))
        if image.isNull():
            raise InspectionDetectorError(f"模板文件无法读取: {template_path}")

        image = image.convertToFormat(QImage.Format_Grayscale8)
        width = image.width()
        height = image.height()
        buffer = image.bits()
        buffer.setsize(height * image.bytesPerLine())
        array = np.frombuffer(buffer, dtype=np.uint8).reshape(height, image.bytesPerLine())[:, :width].copy()
        self._template_image_cache[cache_key] = array
        return array

    def _get_preprocessed_template_roi(
        self,
        template_path: Path,
        template_roi: np.ndarray,
        bbox: BoundingBox,
        grayscale: bool,
        denoise_enabled: bool,
        blur_kernel: int,
        normalize_enabled: bool,
    ) -> np.ndarray:
        cache_key = (
            str(template_path.resolve()),
            grayscale,
            denoise_enabled,
            int(blur_kernel),
            normalize_enabled,
            bbox.x,
            bbox.y,
            bbox.width,
            bbox.height,
        )
        cached = self._template_roi_preprocess_cache.get(cache_key)
        if cached is not None:
            return cached

        processed = apply_preprocess(
            template_roi,
            grayscale=grayscale,
            denoise_enabled=denoise_enabled,
            blur_kernel=blur_kernel,
            normalize_enabled=normalize_enabled,
        )
        self._template_roi_preprocess_cache[cache_key] = processed
        return processed

    def _inspect_single_roi(
        self,
        roi: RoiConfig,
        captured_image: np.ndarray,
        template_image: np.ndarray,
        template_path: Path,
        preprocess,
    ) -> tuple[RoiInspectionResult, float, float]:
        bbox = BoundingBox(x=roi.x, y=roi.y, width=roi.width, height=roi.height)
        if not roi.enabled:
            return (
                RoiInspectionResult(
                    roi_id=roi.id,
                    roi_name=roi.name,
                    index=roi.index,
                    enabled=False,
                    algorithm=roi.algorithm,
                    threshold=roi.threshold,
                    score=None,
                    passed=True,
                    message="已禁用",
                    bbox=bbox,
                ),
                0.0,
                0.0,
            )

        if not self._bbox_inside_image(bbox, captured_image) or not self._bbox_inside_image(bbox, template_image):
            return (
                RoiInspectionResult(
                    roi_id=roi.id,
                    roi_name=roi.name,
                    index=roi.index,
                    enabled=True,
                    algorithm=roi.algorithm,
                    threshold=roi.threshold,
                    score=0.0,
                    passed=False,
                    message="ROI 超出图像边界",
                    bbox=bbox,
                ),
                0.0,
                0.0,
            )

        captured_roi_raw = captured_image[roi.y : roi.y + roi.height, roi.x : roi.x + roi.width]
        template_roi_raw = template_image[roi.y : roi.y + roi.height, roi.x : roi.x + roi.width]
        algorithm = (roi.algorithm or "binary_gray_ratio").strip().lower()

        preprocess_started_at = perf_counter()
        captured_roi = apply_preprocess(
            captured_roi_raw,
            grayscale=preprocess.grayscale,
            denoise_enabled=preprocess.denoise_enabled,
            blur_kernel=preprocess.blur_kernel,
            normalize_enabled=preprocess.normalize_enabled,
        )
        template_roi = self._get_preprocessed_template_roi(
            template_path=template_path,
            template_roi=template_roi_raw,
            bbox=bbox,
            grayscale=preprocess.grayscale,
            denoise_enabled=preprocess.denoise_enabled,
            blur_kernel=preprocess.blur_kernel,
            normalize_enabled=preprocess.normalize_enabled,
        )
        preprocess_ms = (perf_counter() - preprocess_started_at) * 1000.0

        try:
            eval_started_at = perf_counter()
            evaluation = self._evaluate_roi(
                algorithm,
                captured_roi,
                template_roi,
                roi.threshold,
                roi.algorithm_params,
            )
            eval_ms = (perf_counter() - eval_started_at) * 1000.0
        except ValueError as exc:
            return (
                RoiInspectionResult(
                    roi_id=roi.id,
                    roi_name=roi.name,
                    index=roi.index,
                    enabled=True,
                    algorithm=algorithm,
                    threshold=roi.threshold,
                    score=0.0,
                    passed=False,
                    message=str(exc),
                    bbox=bbox,
                ),
                preprocess_ms,
                0.0,
            )

        return (
            RoiInspectionResult(
                roi_id=roi.id,
                roi_name=roi.name,
                index=roi.index,
                enabled=True,
                algorithm=algorithm,
                threshold=roi.threshold,
                score=evaluation.score,
                passed=evaluation.passed,
                message=evaluation.message,
                bbox=bbox,
                predicted_label=evaluation.predicted_label,
                confidence=evaluation.confidence,
                model_name=evaluation.model_name,
                model_version=evaluation.model_version,
                inference_ms=evaluation.inference_ms,
                parallel_algorithm=evaluation.parallel_algorithm,
                parallel_score=evaluation.parallel_score,
                parallel_passed=evaluation.parallel_passed,
                parallel_message=evaluation.parallel_message,
                parallel_predicted_label=evaluation.parallel_predicted_label,
                parallel_confidence=evaluation.parallel_confidence,
                parallel_model_name=evaluation.parallel_model_name,
                parallel_model_version=evaluation.parallel_model_version,
                parallel_inference_ms=evaluation.parallel_inference_ms,
            ),
            preprocess_ms,
            eval_ms,
        )

    def _evaluate_roi(
        self,
        algorithm: str,
        captured_roi: np.ndarray,
        template_roi: np.ndarray,
        threshold: float,
        algorithm_params: dict,
    ) -> AiEvaluationResult:
        primary_params = dict(algorithm_params or {})
        parallel_enabled = self._param_as_bool(primary_params, "parallel_enabled", False)
        parallel_algorithm = str(primary_params.get("parallel_algorithm", "")).strip().lower()
        parallel_threshold = self._param_as_float(primary_params, "parallel_threshold", threshold)
        parallel_params = primary_params.get("parallel_algorithm_params", {})

        evaluation = self._evaluate_algorithm_core(
            algorithm=algorithm,
            captured_roi=captured_roi,
            template_roi=template_roi,
            threshold=threshold,
            algorithm_params=primary_params,
        )

        if not parallel_enabled or not parallel_algorithm:
            return evaluation

        if not isinstance(parallel_params, dict):
            raise ValueError("parallel_algorithm_params 必须为对象")

        parallel_result = self._evaluate_algorithm_core(
            algorithm=parallel_algorithm,
            captured_roi=captured_roi,
            template_roi=template_roi,
            threshold=parallel_threshold,
            algorithm_params=dict(parallel_params),
        )
        evaluation.parallel_algorithm = parallel_algorithm
        evaluation.parallel_score = parallel_result.score
        evaluation.parallel_passed = parallel_result.passed
        evaluation.parallel_message = parallel_result.message
        evaluation.parallel_predicted_label = parallel_result.predicted_label
        evaluation.parallel_confidence = parallel_result.confidence
        evaluation.parallel_model_name = parallel_result.model_name
        evaluation.parallel_model_version = parallel_result.model_version
        evaluation.parallel_inference_ms = parallel_result.inference_ms

        if parallel_result.passed != evaluation.passed:
            evaluation.message = f"{evaluation.message}；并行算法 {parallel_algorithm} 结果 {'OK' if parallel_result.passed else 'NG'}"

        return evaluation

    def _evaluate_algorithm_core(
        self,
        algorithm: str,
        captured_roi: np.ndarray,
        template_roi: np.ndarray,
        threshold: float,
        algorithm_params: dict,
    ) -> AiEvaluationResult:
        if algorithm == "ssim":
            score = compute_ssim_score(captured_roi, template_roi)
            passed = score >= threshold
            return AiEvaluationResult(score=score, passed=passed, message="通过" if passed else "相似度低于阈值")

        if algorithm == "binary_gray_ratio":
            score = self._compute_binary_gray_ratio(captured_roi, algorithm_params)
            threshold_min, threshold_max = self._resolve_binary_ratio_threshold_range(threshold, algorithm_params)
            passed = threshold_min <= score <= threshold_max
            return AiEvaluationResult(
                score=score,
                passed=passed,
                message=(
                    f"二值化面积比例在区间内 ({threshold_min:.3f}-{threshold_max:.3f})"
                    if passed
                    else f"二值化面积比例超出区间 ({threshold_min:.3f}-{threshold_max:.3f})"
                ),
            )

        if algorithm == "ai_classifier":
            return self._evaluate_ai_classifier(captured_roi, threshold, algorithm_params)

        raise ValueError(f"不支持的 ROI 算法: {algorithm}")

    def _resolve_binary_ratio_threshold_range(self, threshold: float, algorithm_params: dict) -> tuple[float, float]:
        threshold_min = self._param_as_float(algorithm_params, "threshold_min", threshold)
        threshold_max = self._param_as_float(algorithm_params, "threshold_max", 1.0)
        threshold_min = max(0.0, min(1.0, threshold_min))
        threshold_max = max(0.0, min(1.0, threshold_max))
        if threshold_max < threshold_min:
            threshold_max = threshold_min
        return threshold_min, threshold_max

    def _evaluate_ai_classifier(
        self,
        roi_image: np.ndarray,
        threshold: float,
        algorithm_params: dict,
    ) -> AiEvaluationResult:
        if ort is None:
            raise ValueError("未安装 onnxruntime，无法使用 ai_classifier")

        resolved_params = self._resolve_ai_algorithm_params(algorithm_params)
        model_path = self._resolve_model_path(resolved_params)
        session = self._get_ai_session(model_path)
        input_name = session.get_inputs()[0].name
        class_names = self._param_as_str_list(resolved_params, "class_names", ["negative", "positive"])
        positive_label = str(resolved_params.get("positive_label") or class_names[-1]).strip() or class_names[-1]
        score_threshold = self._param_as_float(resolved_params, "score_threshold", threshold)
        input_width = self._param_as_int(resolved_params, "input_width", 224)
        input_height = self._param_as_int(resolved_params, "input_height", 224)
        color_mode = str(resolved_params.get("color_mode", "rgb")).strip().lower() or "rgb"
        normalize_to_01 = self._param_as_bool(resolved_params, "normalize_to_01", True)
        mean = self._param_as_float_list(resolved_params, "mean", [0.485, 0.456, 0.406])
        std = self._param_as_float_list(resolved_params, "std", [0.229, 0.224, 0.225])
        model_name = str(resolved_params.get("model_name") or model_path.stem)
        model_version = str(resolved_params.get("model_version") or "")

        input_tensor = self._prepare_ai_input(
            roi_image,
            input_width=input_width,
            input_height=input_height,
            color_mode=color_mode,
            normalize_to_01=normalize_to_01,
            mean=mean,
            std=std,
        )

        started_at = perf_counter()
        outputs = session.run(None, {input_name: input_tensor})
        inference_ms = (perf_counter() - started_at) * 1000.0

        probabilities = self._extract_probabilities(outputs)
        if probabilities.size == 0:
            raise ValueError("ai_classifier 输出为空")

        best_index = int(np.argmax(probabilities))
        if best_index >= len(class_names):
            raise ValueError("ai_classifier 输出类别数与 class_names 不一致")

        predicted_label = class_names[best_index]
        confidence = float(probabilities[best_index])
        positive_index = class_names.index(positive_label) if positive_label in class_names else len(class_names) - 1
        score = float(probabilities[positive_index])
        passed = score >= score_threshold
        message = "AI 分类通过" if passed else "AI 分类未达阈值"

        return AiEvaluationResult(
            score=score,
            passed=passed,
            message=message,
            predicted_label=predicted_label,
            confidence=confidence,
            model_name=model_name,
            model_version=model_version,
            inference_ms=inference_ms,
        )

    def _resolve_ai_algorithm_params(self, algorithm_params: dict) -> dict:
        params = dict(algorithm_params or {})
        model_path = self._resolve_model_path(params)
        meta_path = model_path.with_suffix(".meta.json")
        if not meta_path.exists():
            return params

        try:
            meta_payload = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError(f"AI 模型元数据读取失败: {exc}") from exc

        if not isinstance(meta_payload, dict):
            raise ValueError("AI 模型元数据必须是 JSON 对象")

        merged_params = dict(meta_payload)
        merged_params.update(params)
        merged_params["model_path"] = str(params.get("model_path") or merged_params.get("model_path") or model_path)
        return merged_params

    def _compute_binary_gray_ratio(self, roi_image: np.ndarray, algorithm_params: dict) -> float:
        roi_gray = self._ensure_grayscale(roi_image)
        gray_min = self._param_as_int(algorithm_params, "gray_min", 40)
        gray_max = self._param_as_int(algorithm_params, "gray_max", 160)
        if gray_min > gray_max:
            raise ValueError("binary_gray_ratio 参数错误: gray_min 不能大于 gray_max")

        mask = (roi_gray >= gray_min) & (roi_gray <= gray_max)

        if self._param_as_bool(algorithm_params, "invert", False):
            mask = ~mask

        min_area = max(0, self._param_as_int(algorithm_params, "min_area", 0))
        if min_area > 1:
            mask = self._remove_small_components(mask, min_area)

        return float(np.count_nonzero(mask) / mask.size)

    def _resolve_model_path(self, algorithm_params: dict) -> Path:
        raw_path = str(algorithm_params.get("model_path") or "").strip()
        if not raw_path:
            raise ValueError("ai_classifier 参数错误: model_path 不能为空")

        model_path = Path(raw_path)
        if not model_path.is_absolute():
            model_path = self._data_dir / model_path
        if not model_path.exists():
            raise ValueError(f"AI 模型不存在: {model_path}")
        return model_path

    def _get_ai_session(self, model_path: Path):
        cache_key = str(model_path.resolve())
        session = self._ai_sessions.get(cache_key)
        if session is not None:
            return session

        try:
            session = ort.InferenceSession(cache_key, providers=["CPUExecutionProvider"])
        except Exception as exc:
            raise ValueError(f"AI 模型加载失败: {exc}") from exc

        self._ai_sessions[cache_key] = session
        return session

    def _prepare_ai_input(
        self,
        roi_image: np.ndarray,
        input_width: int,
        input_height: int,
        color_mode: str,
        normalize_to_01: bool,
        mean: list[float],
        std: list[float],
    ) -> np.ndarray:
        if input_width <= 0 or input_height <= 0:
            raise ValueError("ai_classifier 参数错误: 输入尺寸必须大于 0")

        image = self._resize_image(roi_image, input_width, input_height)
        if color_mode == "gray":
            gray_image = self._ensure_grayscale(image).astype(np.float32)
            if normalize_to_01:
                gray_image = gray_image / 255.0
            mean_value = mean[0] if mean else 0.0
            std_value = std[0] if std else 1.0
            if std_value == 0:
                raise ValueError("ai_classifier 参数错误: std 不能为 0")
            gray_image = (gray_image - mean_value) / std_value
            return gray_image[np.newaxis, np.newaxis, :, :].astype(np.float32)

        rgb_image = self._ensure_rgb(image).astype(np.float32)
        if normalize_to_01:
            rgb_image = rgb_image / 255.0
        if len(mean) < 3 or len(std) < 3:
            raise ValueError("ai_classifier 参数错误: RGB 输入要求 mean/std 至少包含 3 个值")
        for channel_index in range(3):
            if std[channel_index] == 0:
                raise ValueError("ai_classifier 参数错误: std 不能为 0")
            rgb_image[:, :, channel_index] = (rgb_image[:, :, channel_index] - mean[channel_index]) / std[channel_index]
        chw_image = np.transpose(rgb_image, (2, 0, 1))
        return chw_image[np.newaxis, :, :, :].astype(np.float32)

    @staticmethod
    def _resize_image(image: np.ndarray, width: int, height: int) -> np.ndarray:
        src_height, src_width = image.shape[:2]
        if src_width == width and src_height == height:
            return image.copy()

        y_indices = np.linspace(0, src_height - 1, height).astype(np.int32)
        x_indices = np.linspace(0, src_width - 1, width).astype(np.int32)
        if image.ndim == 2:
            return image[np.ix_(y_indices, x_indices)].copy()
        return image[np.ix_(y_indices, x_indices, np.arange(image.shape[2]))].copy()

    @staticmethod
    def _ensure_rgb(image: np.ndarray) -> np.ndarray:
        if image.ndim == 2:
            return np.repeat(image[:, :, np.newaxis], 3, axis=2)
        if image.shape[2] >= 3:
            return image[:, :, :3]
        return np.repeat(image[:, :, :1], 3, axis=2)

    @staticmethod
    def _extract_probabilities(outputs: list[np.ndarray]) -> np.ndarray:
        first_output = np.asarray(outputs[0], dtype=np.float32)
        squeezed = np.squeeze(first_output)
        if squeezed.ndim == 0:
            return np.asarray([1.0 - float(squeezed), float(squeezed)], dtype=np.float32)
        if squeezed.ndim != 1:
            raise ValueError("ai_classifier 输出维度不受支持")
        if squeezed.size == 1:
            value = float(squeezed[0])
            return np.asarray([1.0 - value, value], dtype=np.float32)
        exp_values = np.exp(squeezed - np.max(squeezed))
        return exp_values / np.sum(exp_values)

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

    @staticmethod
    def _ensure_grayscale(image: np.ndarray) -> np.ndarray:
        if image.ndim == 2:
            return image
        return np.mean(image[:, :, :3], axis=2).astype(np.uint8)

    @staticmethod
    def _param_as_int(params: dict, key: str, default: int) -> int:
        value = params.get(key, default)
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"参数 {key} 必须为整数") from exc

    @staticmethod
    def _param_as_float(params: dict, key: str, default: float) -> float:
        value = params.get(key, default)
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"参数 {key} 必须为数字") from exc

    @staticmethod
    def _param_as_str_list(params: dict, key: str, default: list[str]) -> list[str]:
        value = params.get(key, default)
        if isinstance(value, str):
            items = [item.strip() for item in value.split(",") if item.strip()]
            return items or list(default)
        if isinstance(value, list):
            items = [str(item).strip() for item in value if str(item).strip()]
            return items or list(default)
        raise ValueError(f"参数 {key} 必须为字符串列表")

    @staticmethod
    def _param_as_float_list(params: dict, key: str, default: list[float]) -> list[float]:
        value = params.get(key, default)
        if isinstance(value, str):
            raw_items = [item.strip() for item in value.split(",") if item.strip()]
        elif isinstance(value, list):
            raw_items = value
        else:
            raise ValueError(f"参数 {key} 必须为数字列表")

        try:
            parsed = [float(item) for item in raw_items]
        except (TypeError, ValueError) as exc:
            raise ValueError(f"参数 {key} 必须为数字列表") from exc
        return parsed or list(default)

    @staticmethod
    def _param_as_bool(params: dict, key: str, default: bool) -> bool:
        value = params.get(key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "y", "on"}:
                return True
            if normalized in {"0", "false", "no", "n", "off"}:
                return False
        return bool(value)

    @staticmethod
    def _bbox_inside_image(bbox: BoundingBox, image: np.ndarray) -> bool:
        height, width = image.shape[:2]
        return bbox.x >= 0 and bbox.y >= 0 and bbox.width > 0 and bbox.height > 0 and bbox.x + bbox.width <= width and bbox.y + bbox.height <= height
