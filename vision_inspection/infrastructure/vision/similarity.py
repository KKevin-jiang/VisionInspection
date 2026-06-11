from __future__ import annotations

import numpy as np


def compute_ssim_score(image_a: np.ndarray, image_b: np.ndarray) -> float:
    if image_a.shape != image_b.shape:
        raise ValueError("images must have the same shape")

    first = image_a.astype(np.float64)
    second = image_b.astype(np.float64)

    mu_first = first.mean()
    mu_second = second.mean()
    sigma_first = ((first - mu_first) ** 2).mean()
    sigma_second = ((second - mu_second) ** 2).mean()
    sigma_cross = ((first - mu_first) * (second - mu_second)).mean()

    c1 = (0.01 * 255) ** 2
    c2 = (0.03 * 255) ** 2

    numerator = (2 * mu_first * mu_second + c1) * (2 * sigma_cross + c2)
    denominator = (mu_first ** 2 + mu_second ** 2 + c1) * (sigma_first + sigma_second + c2)
    if denominator == 0:
        return 1.0 if numerator == 0 else 0.0

    score = numerator / denominator
    return float(max(0.0, min(1.0, score)))
