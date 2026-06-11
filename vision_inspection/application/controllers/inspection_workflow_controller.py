from __future__ import annotations

from vision_inspection.application.services.inspection_workflow_service import InspectionExecutionResult, InspectionWorkflowService
from vision_inspection.domain.models.recipe import RecipeDocument


class InspectionWorkflowController:
    def __init__(self, inspection_workflow_service: InspectionWorkflowService) -> None:
        self._inspection_workflow_service = inspection_workflow_service

    def execute_inspection(
        self,
        recipe_document: RecipeDocument,
        trigger_source: str = "manual",
        preferred_device_index: int = 0,
    ) -> InspectionExecutionResult:
        return self._inspection_workflow_service.execute_inspection(
            recipe_document=recipe_document,
            trigger_source=trigger_source,
            preferred_device_index=preferred_device_index,
        )

    def execute_manual_inspection(
        self,
        recipe_document: RecipeDocument,
        preferred_device_index: int = 0,
    ) -> InspectionExecutionResult:
        return self._inspection_workflow_service.execute_manual_inspection(
            recipe_document=recipe_document,
            preferred_device_index=preferred_device_index,
        )
