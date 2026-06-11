from __future__ import annotations

from pathlib import Path

from vision_inspection.application.services.camera_service import CameraCapture
from vision_inspection.domain.models.inspection_result import InspectionResult
from vision_inspection.domain.models.recipe import RecipeDocument
from vision_inspection.infrastructure.storage.inspection_record_writer import InspectionRecordSaveResult, InspectionRecordWriter


class RecordServiceError(RuntimeError):
    pass


class RecordService:
    def __init__(self, project_root: Path, writer: InspectionRecordWriter | None = None) -> None:
        self._writer = writer or InspectionRecordWriter(project_root)

    def save_inspection_record(
        self,
        recipe_document: RecipeDocument,
        capture: CameraCapture,
        inspection_result: InspectionResult,
        trigger_source: str,
    ) -> InspectionRecordSaveResult:
        try:
            return self._writer.save_record(
                recipe_document=recipe_document,
                capture=capture,
                inspection_result=inspection_result,
                trigger_source=trigger_source,
            )
        except Exception as exc:
            raise RecordServiceError(str(exc)) from exc

    def save_failure_record(
        self,
        recipe_document: RecipeDocument,
        trigger_source: str,
        failure_stage: str,
        failure_message: str,
        capture: CameraCapture | None = None,
        inspection_result: InspectionResult | None = None,
    ) -> InspectionRecordSaveResult:
        try:
            return self._writer.save_failure_record(
                recipe_document=recipe_document,
                trigger_source=trigger_source,
                failure_stage=failure_stage,
                failure_message=failure_message,
                capture=capture,
                inspection_result=inspection_result,
            )
        except Exception as exc:
            raise RecordServiceError(str(exc)) from exc