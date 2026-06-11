from __future__ import annotations

from typing import List, Optional

from vision_inspection.domain.models.recipe import RecipeDocument
from vision_inspection.infrastructure.repositories.recipe_repository import RecipeRepository


class RecipeService:
    def __init__(self, recipe_repository: RecipeRepository) -> None:
        self._recipe_repository = recipe_repository

    def list_recipes(self) -> List[RecipeDocument]:
        return self._recipe_repository.load_all()

    def get_recipe_by_id(self, recipe_id: str) -> Optional[RecipeDocument]:
        for document in self.list_recipes():
            if document.recipe.id == recipe_id:
                return document
        return None

    def get_default_recipe(self) -> Optional[RecipeDocument]:
        recipes = self.list_recipes()
        return recipes[0] if recipes else None

    def save_recipe(self, document: RecipeDocument) -> None:
        self._recipe_repository.save(document)

    def delete_recipe(self, recipe_id: str) -> None:
        self._recipe_repository.delete(recipe_id)
