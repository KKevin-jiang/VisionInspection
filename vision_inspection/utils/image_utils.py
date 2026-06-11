from __future__ import annotations

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None


def resize_image(image: np.ndarray, width: int | None = None, height: int | None = None) -> np.ndarray:
    if width is None and height is None:
        return image.copy()
    h, w = image.shape[:2]
    if width is None:
        ratio = height / h
        width = int(w * ratio)
    elif height is None:
        ratio = width / w
        height = int(h * ratio)
    if cv2 is not None:
        return cv2.resize(image, (width, height), interpolation=cv2.INTER_LINEAR)
    from PIL import Image
    pil_image = Image.fromarray(image)
    pil_image = pil_image.resize((width, height), Image.LANCZOS)
    return np.array(pil_image)


def convert_grayscale(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return image.copy()
    if cv2 is not None:
        return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return np.dot(image[..., :3], [0.114, 0.587, 0.299]).astype(np.uint8)


def draw_roi_boxes(
    image: np.ndarray,
    roi_rects: list[dict],
) -> np.ndarray:
    rendered = image.copy()
    if rendered.ndim == 2:
        if cv2 is not None:
            rendered = cv2.cvtColor(rendered, cv2.COLOR_GRAY2BGR)
        else:
            rendered = np.stack([rendered, rendered, rendered], axis=-1)
    for roi in roi_rects:
        x, y = int(roi["x"]), int(roi["y"])
        w, h = int(roi["width"]), int(roi["height"])
        color_hex = roi.get("color", "#22c55e").lstrip("#")
        r, g, b = int(color_hex[0:2], 16), int(color_hex[2:4], 16), int(color_hex[4:6], 16)
        color = (b, g, r)  # OpenCV BGR
        if cv2 is not None:
            cv2.rectangle(rendered, (x, y), (x + w, y + h), color, 2)
            name = roi.get("name", "")
            if name:
                cv2.putText(
                    rendered, name, (x, max(18, y - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA,
                )
        else:
            rendered[y : y + 2, x : x + w] = color
            rendered[y : y + h, x : x + 2] = color
            rendered[y + h - 2 : y + h, x : x + w] = color
            rendered[y : y + h, x + w - 2 : x + w] = color
    return rendered


def ensure_color(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        if cv2 is not None:
            return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        return np.stack([image, image, image], axis=-1)
    return image.copy()
