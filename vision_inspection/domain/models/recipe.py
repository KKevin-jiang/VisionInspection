from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class RoiConfig:
    id: str
    index: int
    name: str
    enabled: bool
    shape: str
    x: int
    y: int
    width: int
    height: int
    threshold: float
    algorithm: str
    algorithm_params: Dict[str, Any] = field(default_factory=dict)
    score_weight: float = 1.0
    fail_color: str = "#ff3b30"
    pass_color: str = "#22c55e"
    description: str = ""
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RoiConfig":
        return cls(**data)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TemplateConfig:
    id: str
    code: str
    name: str
    enabled: bool
    is_default: bool
    image_path: str
    image_width: int
    image_height: int
    image_checksum: str = ""
    match_priority: int = 1
    roi_list: List[RoiConfig] = field(default_factory=list)
    description: str = ""
    tags: List[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TemplateConfig":
        roi_list = [RoiConfig.from_dict(item) for item in data.get("roi_list", [])]
        payload = dict(data)
        payload["roi_list"] = roi_list
        return cls(**payload)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["roi_list"] = [item.to_dict() for item in self.roi_list]
        return payload


@dataclass
class DecisionPolicy:
    mode: str
    min_pass_count: Optional[int]
    allow_disabled_roi: bool
    final_ng_on_any_fail: bool

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DecisionPolicy":
        return cls(**data)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PreprocessConfig:
    grayscale: bool
    resize_mode: str
    denoise_enabled: bool
    denoise_method: str
    normalize_enabled: bool
    blur_kernel: int

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PreprocessConfig":
        return cls(**data)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class NgOutputConfig:
    enabled: bool
    signal_name: str
    channel: str
    pulse_ms: int
    delay_ms: int
    reset_mode: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NgOutputConfig":
        return cls(**data)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PlcConfig:
    enabled: bool
    trigger_source: str
    protocol: str
    connection: Dict[str, Any]
    ng_output: NgOutputConfig
    heartbeat_enabled: bool
    timeout_ms: int

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlcConfig":
        payload = dict(data)
        payload["ng_output"] = NgOutputConfig.from_dict(data["ng_output"])
        return cls(**payload)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["ng_output"] = self.ng_output.to_dict()
        return payload


@dataclass
class StorageConfig:
    root_dir: str
    save_raw_image: bool
    save_result_image: bool
    save_only_ng_image: bool
    save_json_record: bool
    save_csv_summary: bool
    recipe_subdir_mode: str
    date_subdir_mode: str
    max_retention_days: int

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StorageConfig":
        return cls(**data)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RuntimeConfig:
    target_cycle_ms: int
    detection_timeout_ms: int
    retry_on_capture_fail: int
    allow_manual_test: bool

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RuntimeConfig":
        return cls(**data)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RecipeConfig:
    id: str
    code: str
    name: str
    product_name: str
    product_model: str
    description: str
    station_id: str
    camera_id: str
    enabled: bool
    trigger_mode: str
    template_match_mode: str
    templates: List[TemplateConfig]
    decision_policy: DecisionPolicy
    preprocess: PreprocessConfig
    plc: PlcConfig
    storage: StorageConfig
    runtime: RuntimeConfig
    created_at: str
    updated_at: str
    created_by: str = ""
    updated_by: str = ""
    tags: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RecipeConfig":
        payload = dict(data)
        payload["templates"] = [TemplateConfig.from_dict(item) for item in data.get("templates", [])]
        payload["decision_policy"] = DecisionPolicy.from_dict(data["decision_policy"])
        payload["preprocess"] = PreprocessConfig.from_dict(data["preprocess"])
        payload["plc"] = PlcConfig.from_dict(data["plc"])
        payload["storage"] = StorageConfig.from_dict(data["storage"])
        payload["runtime"] = RuntimeConfig.from_dict(data["runtime"])
        return cls(**payload)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["templates"] = [item.to_dict() for item in self.templates]
        payload["decision_policy"] = self.decision_policy.to_dict()
        payload["preprocess"] = self.preprocess.to_dict()
        payload["plc"] = self.plc.to_dict()
        payload["storage"] = self.storage.to_dict()
        payload["runtime"] = self.runtime.to_dict()
        return payload


@dataclass
class RecipeDocument:
    schema_version: str
    app_version: str
    recipe: RecipeConfig

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RecipeDocument":
        return cls(
            schema_version=data["schema_version"],
            app_version=data["app_version"],
            recipe=RecipeConfig.from_dict(data["recipe"]),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "app_version": self.app_version,
            "recipe": self.recipe.to_dict(),
        }
