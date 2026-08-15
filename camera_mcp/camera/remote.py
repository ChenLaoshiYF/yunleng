"""远程摄像头后端：IP Camera / MJPEG 推流地址。"""

from __future__ import annotations

from typing import Optional, Tuple

import cv2

from .base import CameraBackend, CameraInfo


class RemoteCameraBackend(CameraBackend):
    """远程视频源后端（URL 即地址，如 http://192.168.x.x:8080/video）。"""

    def __init__(self, url: str, cam_id: str = "ip_0"):
        self._url = url
        self._cam_id = cam_id

    @property
    def url(self) -> str:
        return self._url

    def open(self, width: int = 640, height: int = 480):
        cap = cv2.VideoCapture(self._url)
        if not cap.isOpened():
            return None
        try:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        except Exception:
            pass
        return cap

    def read_frame(self, handle):
        if handle is None:
            return None, "远程视频源未打开"
        ret, frame = handle.read()
        if not ret or frame is None:
            return None, "远程视频源读不到帧"
        return frame, None

    def release(self, handle) -> None:
        if handle is not None:
            try:
                handle.release()
            except Exception:
                pass

    def get_property(self, handle, prop_name: str) -> Optional[float]:
        return None  # 远程流不支持属性调节

    def set_property(self, handle, prop_name: str, value: float) -> bool:
        return False

    def probe(self) -> CameraInfo:
        cap = self.open()
        w = h = fps = 0
        if cap is not None:
            try:
                w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
                h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
                fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
            finally:
                cap.release()
        return CameraInfo(
            id=self._cam_id, kind="remote", name=self._url,
            backend="MJPEG-http", width=w, height=h, fps=fps,
            resolutions=[(w, h)] if w and h else [],
        )
