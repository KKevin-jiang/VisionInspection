from __future__ import annotations

import json
from pathlib import Path
from typing import List

from vision_inspection.domain.models.recipe import RecipeDocument


class RecipeRepository:
    def __init__(self, recipes_dir: Path) -> None:
        self._recipes_dir = recipes_dir
        self._recipes_dir.mkdir(parents=True, exist_ok=True)

    def load_all(self) -> List[RecipeDocument]:
        documents = []
        for file_path in sorted(self._recipes_dir.glob("*.json")):
            with file_path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            documents.append(RecipeDocument.from_dict(payload))
        return documents

    def save(self, document: RecipeDocument) -> Path:
        file_path = self._recipes_dir / f"{document.recipe.id}.json"
        with file_path.open("w", encoding="utf-8") as handle:
            json.dump(document.to_dict(), handle, ensure_ascii=False, indent=2)
        return file_path

    def delete(self, recipe_id: str) -> None:
        file_path = self._recipes_dir / f"{recipe_id}.json"
        if not file_path.exists():
            raise FileNotFoundError(f"未找到配方文件: {file_path.name}")
        file_path.unlink()
