from __future__ import annotations

import numpy as np

from vision_inspection.domain.models.inspection_result import InspectionResult
from vision_inspection.domain.models.recipe import RecipeDocument
from vision_inspection.infrastructure.vision import InspectionDetector, InspectionDetectorError


class InspectionServiceError(RuntimeError):
    pass


class InspectionService:
    def __init__(self, detector: InspectionDetector) -> None:
        self._detector = detector

    def inspect_image(self, recipe_document: RecipeDocument, captured_image: np.ndarray) -> InspectionResult:
        try:
            return self._detector.inspect(recipe_document, captured_image)
        except InspectionDetectorError as exc:
            raise InspectionServiceError(str(exc)) from exc
