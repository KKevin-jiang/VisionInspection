from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from vision_inspection.application.services.recipe_service import RecipeService
from vision_inspection.domain.models.recipe import RecipeDocument


@dataclass
class RecipeSummary:
    recipe_id: str
    name: str
    product_name: str
    station_id: str


class RecipeController:
    def __init__(self, recipe_service: RecipeService) -> None:
        self._recipe_service = recipe_service

    def list_recipe_summaries(self) -> List[RecipeSummary]:
        summaries = []
        for document in self._recipe_service.list_recipes():
            recipe = document.recipe
            summaries.append(
                RecipeSummary(
                    recipe_id=recipe.id,
                    name=recipe.name,
                    product_name=recipe.product_name,
                    station_id=recipe.station_id,
                )
            )
        return summaries

    def get_recipe(self, recipe_id: str) -> Optional[RecipeDocument]:
        return self._recipe_service.get_recipe_by_id(recipe_id)

    def get_default_recipe(self) -> Optional[RecipeDocument]:
        return self._recipe_service.get_default_recipe()

    def save_recipe(self, document: RecipeDocument) -> None:
        self._recipe_service.save_recipe(document)

    def delete_recipe(self, recipe_id: str) -> None:
        self._recipe_service.delete_recipe(recipe_id)

    def create_new_recipe_draft(self, source_document: Optional[RecipeDocument] = None) -> RecipeDocument:
        source = deepcopy(source_document or self.get_default_recipe())
        if source is None:
            raise RuntimeError("当前没有可用配方模板，无法新增配方")

        now = self._now_iso()
        recipe_id = self._generate_recipe_id("recipe")
        source.recipe.id = recipe_id
        source.recipe.code = self._generate_recipe_code()
        source.recipe.name = "新配方"
        source.recipe.product_name = ""
        source.recipe.product_model = ""
        source.recipe.description = ""
        source.recipe.storage.save_raw_image = False
        source.recipe.storage.save_result_image = True
        source.recipe.storage.save_only_ng_image = False
        source.recipe.storage.save_json_record = True
        source.recipe.storage.save_csv_summary = False
        source.recipe.created_at = now
        source.recipe.updated_at = now

        for template_index, template in enumerate(source.recipe.templates, start=1):
            template.id = self._generate_template_id(template_index)
            template.code = f"TPL{template_index:03d}"
            template.name = f"模板{template_index}"
            template.image_path = ""
            template.image_width = 0
            template.image_height = 0
            template.created_at = now
            template.updated_at = now
            template.roi_list = []

        return source

    def create_duplicate_recipe_draft(self, source_document: RecipeDocument) -> RecipeDocument:
        duplicated = deepcopy(source_document)
        now = self._now_iso()
        duplicated.recipe.id = self._generate_recipe_id(f"{source_document.recipe.id}-copy")
        duplicated.recipe.code = f"{source_document.recipe.code}-COPY"
        duplicated.recipe.name = f"{source_document.recipe.name}-副本"
        duplicated.recipe.created_at = now
        duplicated.recipe.updated_at = now

        for template_index, template in enumerate(duplicated.recipe.templates, start=1):
            template.id = self._generate_template_id(template_index)
            template.is_default = template_index == 1
            template.created_at = now
            template.updated_at = now
            for roi_index, roi in enumerate(template.roi_list, start=1):
                roi.id = self._generate_roi_id(template_index, roi_index)
                roi.index = roi_index
                roi.created_at = now
                roi.updated_at = now

        return duplicated

    def _generate_recipe_id(self, prefix: str) -> str:
        return f"{prefix}-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    def _generate_recipe_code(self) -> str:
        return f"P{datetime.now().strftime('%H%M%S')}"

    def _generate_template_id(self, index: int) -> str:
        return f"tpl-{datetime.now().strftime('%Y%m%d%H%M%S')}-{index:03d}"

    def _generate_roi_id(self, template_index: int, roi_index: int) -> str:
        return f"roi-{datetime.now().strftime('%Y%m%d%H%M%S')}-{template_index:02d}-{roi_index:03d}"

    def _now_iso(self) -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")
