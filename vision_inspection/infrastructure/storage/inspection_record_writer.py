from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from PyQt5.QtGui import QImage

from vision_inspection.application.services.camera_service import CameraCapture
from vision_inspection.domain.models.inspection_result import InspectionResult
from vision_inspection.domain.models.recipe import RecipeDocument

try:
    import cv2
except ImportError:
    cv2 = None


@dataclass(frozen=True)
class InspectionRecordSaveResult:
    record_id: str
    record_dir: Path
    raw_image_path: Path | None = None
    result_image_path: Path | None = None
    json_record_path: Path | None = None
    csv_summary_path: Path | None = None


class InspectionRecordWriter:
    def __init__(self, project_root: Path) -> None:
        self._project_root = project_root

    def save_record(
        self,
        recipe_document: RecipeDocument,
        capture: CameraCapture,
        inspection_result: InspectionResult,
        trigger_source: str,
    ) -> InspectionRecordSaveResult:
        timestamp = datetime.now()
        record_id = f"{timestamp.strftime('%Y%m%d_%H%M%S_%f')}_{inspection_result.overall_result.lower()}"
        return self._save_record_payload(
            recipe_document=recipe_document,
            capture=capture,
            inspection_result=inspection_result,
            trigger_source=trigger_source,
            record_id=record_id,
            timestamp=timestamp,
            failure_stage=None,
            failure_message="",
        )

    def save_failure_record(
        self,
        recipe_document: RecipeDocument,
        trigger_source: str,
        failure_stage: str,
        failure_message: str,
        capture: CameraCapture | None = None,
        inspection_result: InspectionResult | None = None,
    ) -> InspectionRecordSaveResult:
        timestamp = datetime.now()
        record_id = f"{timestamp.strftime('%Y%m%d_%H%M%S_%f')}_failed_{failure_stage}"
        return self._save_record_payload(
            recipe_document=recipe_document,
            capture=capture,
            inspection_result=inspection_result,
            trigger_source=trigger_source,
            record_id=record_id,
            timestamp=timestamp,
            failure_stage=failure_stage,
            failure_message=failure_message,
        )

    def _save_record_payload(
        self,
        recipe_document: RecipeDocument,
        capture: CameraCapture | None,
        inspection_result: InspectionResult | None,
        trigger_source: str,
        record_id: str,
        timestamp: datetime,
        failure_stage: str | None,
        failure_message: str,
    ) -> InspectionRecordSaveResult:
        record_dir = self._build_record_dir(recipe_document, timestamp)
        record_dir.mkdir(parents=True, exist_ok=True)

        raw_image_path = None
        result_image_path = None
        json_record_path = None
        csv_summary_path = None

        storage = recipe_document.recipe.storage
        overall_result = inspection_result.overall_result if inspection_result is not None else "FAILED"
        should_save_images = (
            capture is not None
            and (not storage.save_only_ng_image or overall_result in {"NG", "FAILED"})
        )

        if storage.save_raw_image and should_save_images and capture is not None:
            raw_image_path = record_dir / f"{record_id}_raw.jpg"
            self._save_image(raw_image_path, capture.frame.image)

        if storage.save_result_image and should_save_images and capture is not None:
            result_image_path = record_dir / f"{record_id}_result.jpg"
            rendered_image = self._render_result_image(
                capture.frame.image,
                inspection_result,
                failure_stage=failure_stage,
                failure_message=failure_message,
            )
            self._save_image(result_image_path, rendered_image)

        payload = self._build_json_payload(
            recipe_document=recipe_document,
            capture=capture,
            inspection_result=inspection_result,
            trigger_source=trigger_source,
            record_id=record_id,
            timestamp=timestamp,
            raw_image_path=raw_image_path,
            result_image_path=result_image_path,
            failure_stage=failure_stage,
            failure_message=failure_message,
        )

        if storage.save_json_record:
            json_record_path = record_dir / f"{record_id}.json"
            json_record_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        if storage.save_csv_summary:
            csv_summary_path = self._build_csv_summary_path(recipe_document, timestamp)
            csv_summary_path.parent.mkdir(parents=True, exist_ok=True)
            self._append_csv_summary(csv_summary_path, payload)

        return InspectionRecordSaveResult(
            record_id=record_id,
            record_dir=record_dir,
            raw_image_path=raw_image_path,
            result_image_path=result_image_path,
            json_record_path=json_record_path,
            csv_summary_path=csv_summary_path,
        )

    def _build_record_dir(self, recipe_document: RecipeDocument, timestamp: datetime) -> Path:
        storage = recipe_document.recipe.storage
        root_dir = Path(storage.root_dir)
        if not root_dir.is_absolute():
            root_dir = self._project_root / root_dir

        record_dir = root_dir / "records"
        if storage.recipe_subdir_mode == "by_recipe":
            record_dir = record_dir / recipe_document.recipe.id
        if storage.date_subdir_mode == "by_day":
            record_dir = record_dir / timestamp.strftime("%Y-%m-%d")
        return record_dir

    def _build_csv_summary_path(self, recipe_document: RecipeDocument, timestamp: datetime) -> Path:
        return self._build_record_dir(recipe_document, timestamp) / "summary.csv"

    def _build_json_payload(
        self,
        recipe_document: RecipeDocument,
        capture: CameraCapture | None,
        inspection_result: InspectionResult | None,
        trigger_source: str,
        record_id: str,
        timestamp: datetime,
        raw_image_path: Path | None,
        result_image_path: Path | None,
        failure_stage: str | None,
        failure_message: str,
    ) -> dict[str, Any]:
        recipe_name = inspection_result.recipe_name if inspection_result is not None else recipe_document.recipe.name
        template_id = inspection_result.template_id if inspection_result is not None else ""
        template_name = inspection_result.template_name if inspection_result is not None else ""
        overall_result = inspection_result.overall_result if inspection_result is not None else "FAILED"
        overall_score = inspection_result.overall_score if inspection_result is not None else None
        error_message = inspection_result.error_message if inspection_result is not None else failure_message
        return {
            "record_id": record_id,
            "timestamp": timestamp.isoformat(),
            "status": "failed" if failure_stage else "completed",
            "trigger_source": trigger_source,
            "failure_stage": failure_stage,
            "recipe_id": recipe_document.recipe.id,
            "recipe_name": recipe_name,
            "template_id": template_id,
            "template_name": template_name,
            "overall_result": overall_result,
            "overall_score": overall_score,
            "error_message": error_message,
            "camera": self._build_camera_payload(capture),
            "storage": {
                "raw_image_path": self._to_relative_path(raw_image_path),
                "result_image_path": self._to_relative_path(result_image_path),
            },
            "plc": recipe_document.recipe.plc.to_dict(),
            "roi_results": [
                {
                    "roi_id": item.roi_id,
                    "roi_name": item.roi_name,
                    "index": item.index,
                    "enabled": item.enabled,
                    "algorithm": item.algorithm,
                    "threshold": item.threshold,
                    "score": item.score,
                    "passed": item.passed,
                    "message": item.message,
                    "predicted_label": item.predicted_label,
                    "confidence": item.confidence,
                    "model_name": item.model_name,
                    "model_version": item.model_version,
                    "inference_ms": item.inference_ms,
                    "parallel_algorithm": item.parallel_algorithm,
                    "parallel_score": item.parallel_score,
                    "parallel_passed": item.parallel_passed,
                    "parallel_message": item.parallel_message,
                    "parallel_predicted_label": item.parallel_predicted_label,
                    "parallel_confidence": item.parallel_confidence,
                    "parallel_model_name": item.parallel_model_name,
                    "parallel_model_version": item.parallel_model_version,
                    "parallel_inference_ms": item.parallel_inference_ms,
                    "bbox": {
                        "x": item.bbox.x,
                        "y": item.bbox.y,
                        "width": item.bbox.width,
                        "height": item.bbox.height,
                    },
                }
                for item in (inspection_result.roi_results if inspection_result is not None else [])
            ],
        }

    def _build_camera_payload(self, capture: CameraCapture | None) -> dict[str, Any] | None:
        if capture is None:
            return None
        return {
            "device_index": capture.device.index,
            "display_name": capture.device.display_name,
            "manufacturer": capture.device.manufacturer,
            "model_name": capture.device.model_name,
            "serial_number": capture.device.serial_number,
            "ip_address": capture.device.ip_address,
            "frame_number": capture.frame.frame_number,
            "width": capture.frame.width,
            "height": capture.frame.height,
            "pixel_type": capture.frame.pixel_type,
        }

    def _append_csv_summary(self, csv_summary_path: Path, payload: dict[str, Any]) -> None:
        fieldnames = [
            "timestamp",
            "record_id",
            "status",
            "failure_stage",
            "trigger_source",
            "recipe_id",
            "recipe_name",
            "template_id",
            "template_name",
            "overall_result",
            "overall_score",
            "frame_number",
            "device_name",
            "ng_count",
            "error_message",
            "raw_image_path",
            "result_image_path",
        ]
        row = {
            "timestamp": payload["timestamp"],
            "record_id": payload["record_id"],
            "status": payload["status"],
            "failure_stage": payload["failure_stage"],
            "trigger_source": payload["trigger_source"],
            "recipe_id": payload["recipe_id"],
            "recipe_name": payload["recipe_name"],
            "template_id": payload["template_id"],
            "template_name": payload["template_name"],
            "overall_result": payload["overall_result"],
            "overall_score": payload["overall_score"],
            "frame_number": payload["camera"]["frame_number"] if payload["camera"] else None,
            "device_name": payload["camera"]["display_name"] if payload["camera"] else None,
            "ng_count": sum(1 for item in payload["roi_results"] if item["enabled"] and not item["passed"]),
            "error_message": payload["error_message"],
            "raw_image_path": payload["storage"]["raw_image_path"],
            "result_image_path": payload["storage"]["result_image_path"],
        }

        write_header = not csv_summary_path.exists()
        with csv_summary_path.open("a", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            if write_header:
                writer.writeheader()
            writer.writerow(row)

    def _render_result_image(
        self,
        image: np.ndarray,
        inspection_result: InspectionResult | None,
        failure_stage: str | None = None,
        failure_message: str = "",
    ) -> np.ndarray:
        rendered = self._to_color_image(image)
        if inspection_result is not None:
            for item in inspection_result.roi_results:
                color = (34, 197, 94) if item.passed else (48, 59, 255)
                x1 = item.bbox.x
                y1 = item.bbox.y
                x2 = item.bbox.x + item.bbox.width
                y2 = item.bbox.y + item.bbox.height

                if cv2 is not None:
                    cv2.rectangle(rendered, (x1, y1), (x2, y2), color, 2)
                    label = f"{item.roi_name}:{'OK' if item.passed else 'NG'}"
                    cv2.putText(
                        rendered,
                        label,
                        (x1, max(18, y1 - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        color,
                        1,
                        cv2.LINE_AA,
                    )
                    continue

                rendered[y1 : y1 + 2, x1:x2] = color
                rendered[max(y1, 0) : y2, x1 : x1 + 2] = color
                rendered[max(y2 - 2, 0) : y2, x1:x2] = color
                rendered[y1:y2, max(x2 - 2, 0) : x2] = color

        if failure_stage:
            self._draw_failure_banner(rendered, failure_stage, failure_message)

        return rendered

    def _draw_failure_banner(self, image: np.ndarray, failure_stage: str, failure_message: str) -> None:
        title = f"FAILED:{failure_stage}"
        if cv2 is not None:
            height = min(40, image.shape[0])
            image[:height, :] = (48, 59, 255)
            cv2.putText(image, title, (8, min(28, height - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
            if failure_message:
                message = failure_message[:80]
                y = min(image.shape[0] - 8, height + 24)
                cv2.putText(image, message, (8, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (48, 59, 255), 1, cv2.LINE_AA)
            return

        banner_height = min(40, image.shape[0])
        image[:banner_height, :] = (48, 59, 255)

    def _to_color_image(self, image: np.ndarray) -> np.ndarray:
        if image.ndim == 2:
            if cv2 is not None:
                return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
            return np.stack([image, image, image], axis=-1).copy()
        return image.copy()

    def _save_image(self, file_path: Path, image: np.ndarray) -> None:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        if cv2 is not None:
            success = cv2.imwrite(str(file_path), image)
            if success:
                return

        qimage = self._numpy_to_qimage(image)
        if not qimage.save(str(file_path)):
            raise RuntimeError(f"图像保存失败: {file_path}")

    def _numpy_to_qimage(self, image: np.ndarray) -> QImage:
        array = np.ascontiguousarray(image)
        if array.ndim == 2:
            height, width = array.shape
            qimage = QImage(array.data, width, height, array.strides[0], QImage.Format_Grayscale8)
            return qimage.copy()

        if array.ndim == 3 and array.shape[2] == 3:
            rgb_array = array
            if cv2 is not None:
                rgb_array = cv2.cvtColor(array, cv2.COLOR_BGR2RGB)
            else:
                rgb_array = array[:, :, ::-1].copy()
            height, width, _ = rgb_array.shape
            qimage = QImage(rgb_array.data, width, height, rgb_array.strides[0], QImage.Format_RGB888)
            return qimage.copy()

        raise RuntimeError("不支持的图像格式，无法保存")

    def _to_relative_path(self, file_path: Path | None) -> str | None:
        if file_path is None:
            return None
        try:
            return str(file_path.relative_to(self._project_root)).replace("\\", "/")
        except ValueError:
            return str(file_path)