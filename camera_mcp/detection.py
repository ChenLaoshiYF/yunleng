"""物体检测模块：基于 YOLO（ultralytics），可选依赖。

不安装 ultralytics 时本模块不影响 server 主流程，
调用 detect_objects 会返回清晰的提示而不是崩溃。

模型默认 yolov8n.pt（首次运行自动下载 ~6MB），
可用环境变量 CAMERA_MCP_YOLO_MODEL 指向自己的权重（如 yolov8s.pt / 自定义 pt）。
"""

from __future__ import annotations

import os
from typing import List, Optional

import numpy as np

_DEFAULT_MODEL = "yolov8n.pt"

# 进程级单例：模型加载很慢，复用一个实例
_model = None


def _get_model():
    global _model
    if _model is None:
        from ultralytics import YOLO  # lazy import，未安装时在此处报错

        path = os.environ.get("CAMERA_MCP_YOLO_MODEL", _DEFAULT_MODEL)
        _model = YOLO(path)
    return _model


def is_available() -> bool:
    """检查 ultralytics 是否已安装（不真正加载模型）。"""
    try:
        import ultralytics  # noqa: F401

        return True
    except ImportError:
        return False


def detect_objects(
    frame_bgr: np.ndarray,
    conf: float = 0.35,
) -> List[dict]:
    """对 BGR 帧做物体检测。

    返回 [{label, confidence, bbox: [x1, y1, x2, y2]}]，按置信度降序。
    """
    model = _get_model()
    results = model.predict(frame_bgr, conf=conf, verbose=False)
    detections: List[dict] = []
    if not results:
        return detections
    r = results[0]
    names = r.names
    boxes = r.boxes
    if boxes is None:
        return detections
    for box in boxes:
        xyxy = [round(float(v), 1) for v in box.xyxy[0].tolist()]
        cls_id = int(box.cls[0])
        detections.append(
            {
                "label": names.get(cls_id, str(cls_id)),
                "confidence": round(float(box.conf[0]), 4),
                "bbox": xyxy,
            }
        )
    detections.sort(key=lambda d: d["confidence"], reverse=True)
    return detections
