from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from vision_inspection.app.config import AppConfig, AppPaths, build_app_paths, load_app_config
from vision_inspection.application.controllers.camera_controller import CameraController
from vision_inspection.application.controllers.inspection_controller import InspectionController
from vision_inspection.application.controllers.inspection_workflow_controller import InspectionWorkflowController
from vision_inspection.application.controllers.plc_controller import PlcController
from vision_inspection.application.controllers.recipe_controller import RecipeController
from vision_inspection.application.services.camera_service import CameraService
from vision_inspection.application.services.inspection_service import InspectionService
from vision_inspection.application.services.inspection_workflow_service import InspectionWorkflowService
from vision_inspection.application.services.plc_service import PlcService
from vision_inspection.application.services.record_service import RecordService
from vision_inspection.application.services.recipe_service import RecipeService
from vision_inspection.infrastructure.plc import MockPlcAdapter
from vision_inspection.infrastructure.repositories.recipe_repository import RecipeRepository
from vision_inspection.infrastructure.vision import InspectionDetector


@dataclass
class AppContainer:
    paths: AppPaths
    recipe_repository: RecipeRepository
    recipe_service: RecipeService
    recipe_controller: RecipeController
    camera_service: CameraService
    camera_controller: CameraController
    inspection_service: InspectionService
    inspection_controller: InspectionController
    record_service: RecordService
    inspection_workflow_service: InspectionWorkflowService
    inspection_workflow_controller: InspectionWorkflowController
    plc_service: PlcService
    plc_controller: PlcController


def build_container(project_root):
    app_config = load_app_config(project_root)
    paths = build_app_paths(project_root, app_config)
    recipe_repository = RecipeRepository(paths.recipes_dir)
    recipe_service = RecipeService(recipe_repository)
    recipe_controller = RecipeController(recipe_service)
    camera_service = CameraService()
    camera_controller = CameraController(camera_service)
    inspection_detector = InspectionDetector(paths.data_dir)
    inspection_service = InspectionService(inspection_detector)
    inspection_controller = InspectionController(inspection_service)
    record_service = RecordService(Path(app_config.storage.image_root))
    plc_service = PlcService(adapter_factory=MockPlcAdapter)
    plc_controller = PlcController(plc_service)
    inspection_workflow_service = InspectionWorkflowService(camera_service, inspection_service, record_service, plc_service)
    inspection_workflow_controller = InspectionWorkflowController(inspection_workflow_service)
    return AppContainer(
        paths=paths,
        recipe_repository=recipe_repository,
        recipe_service=recipe_service,
        recipe_controller=recipe_controller,
        camera_service=camera_service,
        camera_controller=camera_controller,
        inspection_service=inspection_service,
        inspection_controller=inspection_controller,
        record_service=record_service,
        inspection_workflow_service=inspection_workflow_service,
        inspection_workflow_controller=inspection_workflow_controller,
        plc_service=plc_service,
        plc_controller=plc_controller,
    )
