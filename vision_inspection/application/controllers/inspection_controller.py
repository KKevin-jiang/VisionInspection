from __future__ import annotations

import numpy as np

from vision_inspection.application.services.inspection_service import InspectionService
from vision_inspection.domain.models.inspection_result import InspectionResult
from vision_inspection.domain.models.recipe import RecipeDocument


class InspectionController:
    def __init__(self, inspection_service: InspectionService) -> None:
        self._inspection_service = inspection_service

    def inspect_image(self, recipe_document: RecipeDocument, captured_image: np.ndarray) -> InspectionResult:
        return self._inspection_service.inspect_image(recipe_document, captured_image)
