"""摄像头子系统：后端抽象 + 本地/远程实现 + 管理器。"""

from .base import CameraBackend, CameraInfo
from .local import LocalCameraBackend, open_camera
from .manager import CameraManager
from .remote import RemoteCameraBackend

# 单例管理器（server.py 用 camera.manager 直接访问）
manager = CameraManager()

__all__ = [
    "CameraBackend",
    "CameraInfo",
    "CameraManager",
    "LocalCameraBackend",
    "RemoteCameraBackend",
    "manager",
    "open_camera",
]
