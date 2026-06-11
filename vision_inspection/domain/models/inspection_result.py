from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class BoundingBox:
    x: int
    y: int
    width: int
    height: int


@dataclass
class RoiInspectionResult:
    roi_id: str
    roi_name: str
    index: int
    enabled: bool
    algorithm: str
    threshold: float
    score: Optional[float]
    passed: bool
    message: str
    bbox: BoundingBox
    predicted_label: str = ""
    confidence: Optional[float] = None
    model_name: str = ""
    model_version: str = ""
    inference_ms: Optional[float] = None
    parallel_algorithm: str = ""
    parallel_score: Optional[float] = None
    parallel_passed: Optional[bool] = None
    parallel_message: str = ""
    parallel_predicted_label: str = ""
    parallel_confidence: Optional[float] = None
    parallel_model_name: str = ""
    parallel_model_version: str = ""
    parallel_inference_ms: Optional[float] = None


@dataclass
class InspectionResult:
    recipe_id: str
    recipe_name: str
    template_id: str
    template_name: str
    overall_result: str
    roi_results: List[RoiInspectionResult] = field(default_factory=list)
    overall_score: Optional[float] = None
    error_message: str = ""
    phase_metrics: dict[str, float] = field(default_factory=dict)
