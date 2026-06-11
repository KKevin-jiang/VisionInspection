from __future__ import annotations

from typing import Optional

import numpy as np

try:
    import cv2
except ImportError:  # pragma: no cover - optional dependency
    cv2 = None


def to_grayscale(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return image.copy()
    if image.ndim == 3 and image.shape[2] == 3:
        if cv2 is not None:
            return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        return np.dot(image[..., :3], [0.114, 0.587, 0.299]).astype(np.uint8)
    raise ValueError("unsupported image format")


def apply_preprocess(
    image: np.ndarray,
    grayscale: bool = True,
    denoise_enabled: bool = False,
    blur_kernel: int = 3,
    normalize_enabled: bool = False,
) -> np.ndarray:
    processed = to_grayscale(image) if grayscale else image.copy()

    if denoise_enabled and cv2 is not None:
        kernel = max(1, int(blur_kernel))
        if kernel % 2 == 0:
            kernel += 1
        processed = cv2.GaussianBlur(processed, (kernel, kernel), 0)

    if normalize_enabled:
        min_value = float(processed.min())
        max_value = float(processed.max())
        if max_value > min_value:
            processed = ((processed - min_value) / (max_value - min_value) * 255.0).astype(np.uint8)

    return processed
