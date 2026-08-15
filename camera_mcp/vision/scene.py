"""场景感知与画面增强：从原 camera.py 独立出来的视觉处理模块。"""

from __future__ import annotations

from typing import Optional

import cv2
import numpy as np

SCENES = ("dark", "normal", "overexposed")


def detect_scene(frame: np.ndarray) -> dict:
    """按亮度与直方图分布判断暗光/正常/过曝，返回 {scene, confidence, metrics}。"""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    mean_b = float(gray.mean())
    hist = cv2.calcHist([gray], [0], None, [256], [0, 256]).flatten()
    total = max(float(hist.sum()), 1.0)
    dark_ratio = float(hist[:70].sum()) / total   # 暗部像素占比
    bright_ratio = float(hist[186:].sum()) / total  # 亮部像素占比
    if mean_b < 70 or dark_ratio > 0.5:
        scene, conf = "dark", 0.8
    elif mean_b > 200 or bright_ratio > 0.5:
        scene, conf = "overexposed", 0.75
    else:
        scene, conf = "normal", 0.6
    return {
        "scene": scene, "confidence": conf,
        "metrics": {"mean_brightness": round(mean_b, 1),
                    "dark_ratio": round(dark_ratio, 3),
                    "bright_ratio": round(bright_ratio, 3)},
    }


def clahe(img: np.ndarray, clip: float = 2.0, tile: int = 8) -> np.ndarray:
    """自适应直方图均衡：LAB 的 L 通道做，拉细节不动颜色。"""
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    l = cv2.createCLAHE(clip, (tile, tile)).apply(l)
    return cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)


def sharpen(img: np.ndarray, amount: float = 1.5, sigma: float = 1.0) -> np.ndarray:
    """Unsharp masking：原图 + 高斯模糊层差值增强边缘。"""
    blur = cv2.GaussianBlur(img, (0, 0), sigma)
    return cv2.addWeighted(img, 1 + amount, blur, -amount, 0)


def auto_enhance(frame: np.ndarray) -> np.ndarray:
    """一键美化：CLAHE 暗部细节 + 轻微锐化。"""
    return sharpen(clahe(frame))


def software_correct(frame: np.ndarray, scene_info: Optional[dict] = None) -> np.ndarray:
    """软件兜底校正：暗光伽马提亮 / 过曝压暗 + 灰度世界白平衡，任何摄像头都有效。"""
    scene_info = scene_info or detect_scene(frame)
    out = frame.astype(np.float32)
    scene = scene_info.get("scene", "normal")
    if scene == "dark":
        out = 255.0 * np.power(out / 255.0, 0.75)
    elif scene == "overexposed":
        out = 255.0 * np.power(out / 255.0, 1.25)
    elif scene_info.get("metrics", {}).get("mean_brightness", 128) < 90:
        out = 255.0 * np.power(out / 255.0, 0.85)
    b, g, r = out[:, :, 0].mean(), out[:, :, 1].mean(), out[:, :, 2].mean()
    avg = (b + g + r) / 3.0
    if avg > 1:
        for i in range(3):
            out[:, :, i] *= max(0.3, min(3.0, avg / [b, g, r][i]))
    return np.clip(out, 0, 255).astype(np.uint8)
