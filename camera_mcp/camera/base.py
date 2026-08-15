"""摄像头后端抽象：定义统一接口，本地/远程各自实现。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class CameraInfo:
    """一个摄像头（本地或远程）的基本信息。"""

    id: str
    kind: str  # "local" / "remote"
    name: str
    backend: str
    width: int
    height: int
    fps: float
    resolutions: List[Tuple[int, int]] = field(default_factory=list)
    lens_type: str = "unknown"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "name": self.name,
            "backend": self.backend,
            "width": self.width,
            "height": self.height,
            "fps": round(self.fps, 2) if self.fps else 0.0,
            "resolutions": [list(r) for r in self.resolutions],
            "lens_type": self.lens_type,
        }


class CameraBackend(ABC):
    """摄像头后端接口：所有摄像头实现（本地/远程）遵循同一契约。"""

    @abstractmethod
    def open(self, width: int = 640, height: int = 480):
        """打开摄像头，返回可用句柄（实现方定义类型）。"""

    @abstractmethod
    def read_frame(self, handle) -> Tuple[Optional[object], Optional[str]]:
        """读一帧，返回 (BGR ndarray, error)。"""

    @abstractmethod
    def release(self, handle) -> None:
        """释放句柄。"""

    @abstractmethod
    def get_property(self, handle, prop_name: str) -> Optional[float]:
        """读属性值（None = 不支持）。"""

    @abstractmethod
    def set_property(self, handle, prop_name: str, value: float) -> bool:
        """设置属性值。"""

    @abstractmethod
    def probe(self) -> CameraInfo:
        """探测并返回本后端的完整信息。"""
