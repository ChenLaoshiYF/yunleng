"""本地摄像头后端：基于 OpenCV VideoCapture（Windows MSMF/DSHOW）。"""

from __future__ import annotations

import time
from typing import Dict, List, Optional, Tuple

import cv2

from .base import CameraBackend, CameraInfo

_BACKENDS = (cv2.CAP_MSMF, 0, cv2.CAP_DSHOW)  # 后端尝试顺序
_MAX_INDEX = 8  # 本地摄像头最多探测的 index 数
_RESOLUTION_CANDIDATES = [(1920, 1080), (1280, 720), (640, 480), (320, 240)]

# 可调属性白名单：名称 → CAP_PROP 常量
_PROPERTIES: Dict[str, int] = {
    "brightness": cv2.CAP_PROP_BRIGHTNESS,
    "contrast": cv2.CAP_PROP_CONTRAST,
    "saturation": cv2.CAP_PROP_SATURATION,
    "hue": cv2.CAP_PROP_HUE,
    "gain": cv2.CAP_PROP_GAIN,
    "exposure": cv2.CAP_PROP_EXPOSURE,
    "focus": cv2.CAP_PROP_FOCUS,
    "zoom": cv2.CAP_PROP_ZOOM,
    "sharpness": cv2.CAP_PROP_SHARPNESS,
    "gamma": cv2.CAP_PROP_GAMMA,
    "white_balance_blue_u": cv2.CAP_PROP_WHITE_BALANCE_BLUE_U,
    "white_balance_red_v": cv2.CAP_PROP_WHITE_BALANCE_RED_V,
    "autofocus": cv2.CAP_PROP_AUTOFOCUS,
    "auto_exposure": cv2.CAP_PROP_AUTO_EXPOSURE,
    "backlight": cv2.CAP_PROP_BACKLIGHT,
    "iso_speed": cv2.CAP_PROP_ISO_SPEED,
    "temperature": cv2.CAP_PROP_TEMPERATURE,
    "pan": cv2.CAP_PROP_PAN,
    "tilt": cv2.CAP_PROP_TILT,
    "roll": cv2.CAP_PROP_ROLL,
}


class LocalCameraBackend(CameraBackend):
    """本地 USB 摄像头后端（cv2.VideoCapture + index）。"""

    def __init__(self, index: int = 0):
        self._index = index

    def open(self, width: int = 640, height: int = 480):
        return open_camera(self._index, width, height)

    def read_frame(self, handle):
        if handle is None:
            return None, "摄像头未打开"
        ret, frame = handle.read()
        if not ret or frame is None:
            return None, "读取帧失败"
        return frame, None

    def release(self, handle) -> None:
        if handle is not None:
            try:
                handle.release()
            except Exception:
                pass

    def get_property(self, handle, prop_name: str) -> Optional[float]:
        prop = _PROPERTIES.get(prop_name)
        if prop is None or handle is None:
            return None
        return _read_prop(handle, prop)

    def set_property(self, handle, prop_name: str, value: float) -> bool:
        prop = _PROPERTIES.get(prop_name)
        if prop is None or handle is None:
            return False
        try:
            return bool(handle.set(prop, value))
        except Exception:
            return False

    def probe(self) -> CameraInfo:
        cap = open_camera(self._index, retries=2)
        w = h = fps = 0
        backend = "unknown"
        if cap is not None:
            try:
                w = int(_read_prop(cap, cv2.CAP_PROP_FRAME_WIDTH) or 0)
                h = int(_read_prop(cap, cv2.CAP_PROP_FRAME_HEIGHT) or 0)
                fps = float(_read_prop(cap, cv2.CAP_PROP_FPS) or 0.0)
                backend = _backend_name(cap) or "unknown"
            finally:
                cap.release()
        info = CameraInfo(
            id=str(self._index), kind="local", name=f"Camera {self._index}",
            backend=backend, width=w, height=h, fps=fps,
            resolutions=self._probe_resolutions() or ([(w, h)] if w and h else []),
        )
        if info.resolutions:
            max_w = max(ww for ww, _ in info.resolutions)
            info.lens_type = "wide" if max_w >= 1280 else "unknown"
        return info

    def _probe_resolutions(self) -> List[Tuple[int, int]]:
        """独立临时 cap 探测关键候选分辨率，set 后读回实际生效值，探测完释放。"""
        cap = open_camera(self._index, retries=2)
        if cap is None:
            return []
        found: List[Tuple[int, int]] = []
        try:
            for w, h in _RESOLUTION_CANDIDATES:
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
                got_w = int(_read_prop(cap, cv2.CAP_PROP_FRAME_WIDTH) or 0)
                got_h = int(_read_prop(cap, cv2.CAP_PROP_FRAME_HEIGHT) or 0)
                if got_w and got_h and (got_w, got_h) not in found:
                    if abs(got_w - w) <= w * 0.02 and abs(got_h - h) <= h * 0.02:
                        found.append((got_w, got_h))
        finally:
            cap.release()
            time.sleep(0.2)  # 让驱动从分辨率切换中复位，避免影响后续 capture
        return found


def open_camera(
    index: int = 0,
    width: int = 640,
    height: int = 480,
    retries: int = 10,
    backend: int = 0,
) -> Optional[cv2.VideoCapture]:
    """打开摄像头并完成冷启动预热；backend=0 时按 _BACKENDS 顺序尝试。"""
    backends = (backend,) if backend else _BACKENDS
    for b in backends:
        cap = None
        try:
            cap = cv2.VideoCapture(index, b) if b else cv2.VideoCapture(index)
            if not cap.isOpened():
                cap.release()
                cap = None
                continue
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            for _ in range(retries):
                ret, _ = cap.read()
                if ret:
                    return cap
                time.sleep(0.15)
            cap.release()
            cap = None
        except Exception:
            if cap is not None:
                cap.release()
            cap = None
    return None


def _read_prop(cap: cv2.VideoCapture, prop: int) -> Optional[float]:
    try:
        v = cap.get(prop)
        return float(v) if v is not None and v != -1.0 else None
    except Exception:
        return None


def _backend_name(cap: cv2.VideoCapture) -> str:
    try:
        return cap.getBackendName() or "unknown"
    except Exception:
        return "unknown"


def discover_local_cameras() -> List[CameraInfo]:
    """探测全部本地摄像头。"""
    infos: List[CameraInfo] = []
    for i in range(_MAX_INDEX):
        backend = LocalCameraBackend(i)
        info = backend.probe()
        if info.width and info.height:
            infos.append(info)
    return infos
