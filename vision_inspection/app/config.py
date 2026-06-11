from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CameraParamsConfig:
    exposure_us: float = 5000
    gain_raw: float = 0
    gamma: float = 1.0
    frame_rate: float = 30.0
    digital_gain: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "exposure_us": self.exposure_us,
            "gain_raw": self.gain_raw,
            "gamma": self.gamma,
            "frame_rate": self.frame_rate,
            "digital_gain": self.digital_gain,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CameraParamsConfig":
        return cls(
            exposure_us=float(data.get("exposure_us", 5000)),
            gain_raw=float(data.get("gain_raw", 0)),
            gamma=float(data.get("gamma", 1.0)),
            frame_rate=float(data.get("frame_rate", 30.0)),
            digital_gain=float(data.get("digital_gain", 1.0)),
        )


@dataclass
class DatabaseConfig:
    server: str = r"192.168.0.101\SQL201"
    database: str = "BLT"
    username: str = "sa"
    password: str = "123456"
    serial_table: str = "T_SerialNo"
    serial_field: str = "ActSerialNo"
    model_field: str = "MachineType"
    result_table: str = "T_VisionResult"
    station_id: str = "ST001"

    def to_dict(self) -> dict[str, Any]:
        return {
            "server": self.server,
            "database": self.database,
            "username": self.username,
            "password": self.password,
            "serial_table": self.serial_table,
            "serial_field": self.serial_field,
            "model_field": self.model_field,
            "result_table": self.result_table,
            "station_id": self.station_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DatabaseConfig":
        return cls(
            server=data.get("server", cls.server),
            database=data.get("database", cls.database),
            username=data.get("username", cls.username),
            password=data.get("password", cls.password),
            serial_table=data.get("serial_table", cls.serial_table),
            serial_field=data.get("serial_field", cls.serial_field),
            model_field=data.get("model_field", cls.model_field),
            result_table=data.get("result_table", cls.result_table),
            station_id=data.get("station_id", cls.station_id),
        )


@dataclass
class CrankshaftApiConfig:
    base_url: str = "http://192.168.0.101:8080"
    timeout_ms: int = 1500
    source: str = "vision-inspection"

    def to_dict(self) -> dict[str, Any]:
        return {
            "base_url": self.base_url,
            "timeout_ms": self.timeout_ms,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CrankshaftApiConfig":
        return cls(
            base_url=data.get("base_url", cls.base_url),
            timeout_ms=int(data.get("timeout_ms", cls.timeout_ms)),
            source=data.get("source", cls.source),
        )


@dataclass
class StorageConfig:
    image_root: str = "D:\\VisionImages"
    save_pass_images: bool = True
    log_root: str = "D:\\VisionLogs"

    def to_dict(self) -> dict[str, Any]:
        return {
            "image_root": self.image_root,
            "save_pass_images": self.save_pass_images,
            "log_root": self.log_root,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StorageConfig":
        return cls(
            image_root=data.get("image_root", cls.image_root),
            save_pass_images=bool(data.get("save_pass_images", cls.save_pass_images)),
            log_root=data.get("log_root", cls.log_root),
        )


@dataclass
class IoConfig:
    line1_pass_duration_ms: int = 500

    def to_dict(self) -> dict[str, Any]:
        return {"line1_pass_duration_ms": self.line1_pass_duration_ms}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IoConfig":
        return cls(line1_pass_duration_ms=int(data.get("line1_pass_duration_ms", 500)))


@dataclass
class AppConfig:
    camera_params: CameraParamsConfig = field(default_factory=CameraParamsConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    crankshaft_api: CrankshaftApiConfig = field(default_factory=CrankshaftApiConfig)
    switch_mode: str = "auto"
    storage: StorageConfig = field(default_factory=StorageConfig)
    io: IoConfig = field(default_factory=IoConfig)

    def to_dict(self) -> dict[str, Any]:
        return {
            "camera": self.camera_params.to_dict(),
            "database": self.database.to_dict(),
            "crankshaft_api": self.crankshaft_api.to_dict(),
            "switch_mode": self.switch_mode,
            "storage": self.storage.to_dict(),
            "io": self.io.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppConfig":
        camera_data = data.get("camera", {})
        db_data = data.get("database", {})
        api_data = data.get("crankshaft_api", {})
        storage_data = data.get("storage", {})
        io_data = data.get("io", {})
        return cls(
            camera_params=CameraParamsConfig.from_dict(camera_data),
            database=DatabaseConfig.from_dict(db_data),
            crankshaft_api=CrankshaftApiConfig.from_dict(api_data),
            switch_mode=data.get("switch_mode", "auto"),
            storage=StorageConfig.from_dict(storage_data),
            io=IoConfig.from_dict(io_data),
        )


def load_app_config(project_root: Path) -> AppConfig:
    config_path = project_root / "app_config.json"
    if not config_path.exists():
        return AppConfig()
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return AppConfig.from_dict(data)
    except (json.JSONDecodeError, KeyError, TypeError):
        return AppConfig()


def save_app_config(config: AppConfig, project_root: Path) -> None:
    config_path = project_root / "app_config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config.to_dict(), f, indent=2, ensure_ascii=False)


@dataclass(frozen=True)
class AppPaths:
    project_root: Path
    data_dir: Path
    recipes_dir: Path
    templates_dir: Path
    records_dir: Path
    logs_dir: Path


def build_app_paths(project_root: Path) -> AppPaths:
    data_dir = project_root / "data"
    return AppPaths(
        project_root=project_root,
        data_dir=data_dir,
        recipes_dir=data_dir / "recipes",
        templates_dir=data_dir / "templates",
        records_dir=data_dir / "records",
        logs_dir=data_dir / "logs",
    )
