"""摄像头管理器：统一调度本地/远程后端，维护缓存与生命周期。"""

from __future__ import annotations

import threading
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from .base import CameraBackend, CameraInfo
from .local import LocalCameraBackend, discover_local_cameras
from .remote import RemoteCameraBackend


class CameraManager:
    """摄像头管理：枚举 / 拍帧 / 双摄 / 远程注册 / 属性控制 / 智能拍照。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._local: Optional[List[CameraInfo]] = None
        self._remote: Dict[str, RemoteCameraBackend] = {}
        self._remote_seq = 0

    # --- 枚举与探测 ---
    def discover(self, refresh: bool = False) -> List[CameraInfo]:
        """枚举所有摄像头（本地 + 远程）；本地结果缓存，refresh 强制重探。"""
        with self._lock:
            if self._local is not None and not refresh:
                return self._local + [b.probe() for b in self._remote.values()]
            self._local = discover_local_cameras()
            return self._local + [b.probe() for b in self._remote.values()]

    # --- 远程摄像头（IP Camera） ---
    def add_remote(self, url: str) -> CameraInfo:
        """注册远程视频源（IP Camera 推流地址），验证可读后登记为 ip_N。"""
        backend = RemoteCameraBackend(url, cam_id=f"ip_{self._remote_seq}")
        cap = backend.open()
        if cap is None:
            raise ValueError(f"无法打开远程视频源: {url}")
        try:
            ret, _ = backend.read_frame(cap)
            if ret is None:
                raise ValueError(f"远程视频源读不到帧: {url}")
        finally:
            backend.release(cap)
        with self._lock:
            self._remote[backend._cam_id] = backend
            self._remote_seq += 1
            info = backend.probe()
            info.id = backend._cam_id
            return info

    def remove_remote(self, cam_id: str) -> bool:
        with self._lock:
            if cam_id in self._remote:
                del self._remote[cam_id]
                return True
        return False

    # --- 拍帧 ---
    def _resolve(self, cam_id: str) -> Tuple[Optional[CameraBackend], Optional[CameraInfo], str]:
        """把 cam_id 解析成后端实例：'0' → 本地 index；'ip_0' → 远程。"""
        with self._lock:
            if cam_id in self._remote:
                backend = self._remote[cam_id]
                return backend, backend.probe(), ""
        if cam_id.isdigit():
            for info in self.discover():
                if info.kind == "local" and info.id == cam_id:
                    return LocalCameraBackend(int(cam_id)), info, ""
            return None, None, f"本地摄像头 index={cam_id} 未探测到"
        return None, None, f"未知摄像头 id: {cam_id}（可用 list_cameras 查看）"

    def capture(
        self, cam_id: str, width: int = 640, height: int = 480, jpeg_quality: int = 90
    ) -> Tuple[Optional[np.ndarray], Optional[bytes], Optional[str]]:
        """按 cam_id 拍一帧，返回 (BGR 帧, JPEG bytes, error)。用完即释放。"""
        backend, info, err = self._resolve(cam_id)
        if backend is None or info is None:
            return None, None, err
        cap = backend.open(width, height)
        if cap is None:
            return None, None, f"无法打开摄像头 {cam_id}"
        try:
            frame, rerr = backend.read_frame(cap)
            if frame is None:
                return None, None, rerr or f"摄像头 {cam_id} 读取帧失败"
            ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality])
            if not ok:
                return None, None, "JPEG 编码失败"
            return frame, buf.tobytes(), None
        finally:
            backend.release(cap)

    def capture_stereo(
        self,
        cam1_id: str,
        cam2_id: str,
        width: int = 640,
        height: int = 480,
        jpeg_quality: int = 85,
    ) -> dict:
        """两路交替读帧（Windows 后端非线程安全，串行间隔最小），返回对齐报告。"""
        b1, i1, e1 = self._resolve(cam1_id)
        b2, i2, e2 = self._resolve(cam2_id)
        if b1 is None or b2 is None or i1 is None or i2 is None:
            return {"ok": False, "error": e1 or e2}
        cap1 = b1.open(width, height)
        cap2 = b2.open(width, height)
        if cap1 is None or cap2 is None:
            for b, c in ((b1, cap1), (b2, cap2)):
                b.release(c)
            return {"ok": False, "error": "至少一路摄像头无法打开"}
        try:
            b1.read_frame(cap1)
            b2.read_frame(cap2)
            r1, fr1 = b1.read_frame(cap1)
            t1 = _now_ms()
            r2, fr2 = b2.read_frame(cap2)
            t2 = _now_ms()
            frames = []
            for cam_id, backend, ret, frame, t in ((cam1_id, b1, r1, fr1, t1), (cam2_id, b2, r2, fr2, t2)):
                if ret is None or frame is None:
                    continue
                ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality])
                if ok:
                    frames.append({
                        "camera_id": cam_id,
                        "timestamp_ms": t,
                        "jpeg_base64": _b64(buf.tobytes()),
                    })
            if len(frames) < 2:
                return {"ok": False, "error": "两路摄像头未都读到帧"}
            gap_ms = abs(frames[1]["timestamp_ms"] - frames[0]["timestamp_ms"])
            return {"ok": True, "frames": frames, "sync_gap_ms": round(gap_ms, 2)}
        finally:
            b1.release(cap1)
            b2.release(cap2)

    # --- 属性控制 ---
    def list_properties(self, cam_id: str) -> List[dict]:
        """读全部候选属性当前值，读不到即不支持。"""
        backend, info, _ = self._resolve(cam_id)
        if backend is None or info is None:
            return []
        cap = backend.open()
        if cap is None:
            return []
        try:
            names = [
                "brightness", "contrast", "saturation", "hue", "gain", "exposure",
                "focus", "zoom", "sharpness", "gamma", "white_balance_blue_u",
                "white_balance_red_v", "autofocus", "auto_exposure", "backlight",
                "iso_speed", "temperature", "pan", "tilt", "roll",
            ]
            props = []
            for name in names:
                v = backend.get_property(cap, name)
                props.append({
                    "name": name,
                    "value": round(v, 2) if v is not None else None,
                    "supported": v is not None,
                })
            return props
        finally:
            backend.release(cap)

    def set_property(self, cam_id: str, prop_name: str, value: float) -> dict:
        """设置属性并读回确认。"""
        backend, info, _ = self._resolve(cam_id)
        if backend is None or info is None:
            return {"ok": False, "error": f"未知摄像头: {cam_id}"}
        cap = backend.open()
        if cap is None:
            return {"ok": False, "error": f"无法打开摄像头 {cam_id}"}
        try:
            ok = backend.set_property(cap, prop_name, value)
            readback = backend.get_property(cap, prop_name)
            return {
                "ok": True,
                "camera_id": cam_id,
                "property": prop_name,
                "requested": value,
                "set_ack": bool(ok),
                "actual_value": round(readback, 2) if readback is not None else None,
            }
        finally:
            backend.release(cap)

    def get_properties(self, cam_id: str) -> dict:
        """返回摄像头当前所有可调属性的值（读不到即不支持）。"""
        backend, info, err = self._resolve(cam_id)
        if backend is None or info is None:
            return {"ok": False, "error": err}
        cap = backend.open()
        if cap is None:
            return {"ok": False, "error": f"无法打开摄像头 {cam_id}"}
        try:
            props = {}
            for item in self.list_properties(cam_id):
                props[item["name"]] = {
                    "value": item["value"],
                    "supported": item["supported"],
                }
            return {"ok": True, "camera_id": cam_id, "properties": props}
        finally:
            backend.release(cap)

    # --- 对焦 / 曝光（软件级，尽力而为） ---
    def auto_focus(self, cam_id: str, frames: int = 6, width: int = 640, height: int = 480) -> dict:
        """连拍 N 帧取 Laplacian 方差最高的一帧（软件模拟对焦）。"""
        backend, info, err = self._resolve(cam_id)
        if backend is None or info is None:
            return {"ok": False, "error": err}
        cap = backend.open(width, height)
        if cap is None:
            return {"ok": False, "error": f"无法打开摄像头 {cam_id}"}
        try:
            best, best_score, best_i = None, -1.0, -1
            for i in range(frames):
                frame, rerr = backend.read_frame(cap)
                if frame is not None:
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    s = float(cv2.Laplacian(gray, cv2.CV_64F).var())
                    if s > best_score:
                        best, best_score, best_i = frame, s, i
                import time
                time.sleep(0.05)
            if best is None:
                return {"ok": False, "error": "连拍失败，无法对焦"}
            ok, buf = cv2.imencode(".jpg", best, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
            return {
                "ok": True,
                "camera_id": cam_id,
                "sharpness": round(best_score, 1),
                "frame_index": best_i,
                "jpeg_base64": "data:image/jpeg;base64," + _b64(buf.tobytes()),
            }
        finally:
            backend.release(cap)

    def set_exposure(self, cam_id: str, mode: str = "auto", value: Optional[float] = None) -> dict:
        """曝光控制：mode=auto 自动曝光；mode=manual 切手动，value 可选。"""
        if mode not in ("auto", "manual"):
            return {"ok": False, "error": f"mode 必须为 auto/manual，收到 {mode}"}
        backend, info, err = self._resolve(cam_id)
        if backend is None or info is None:
            return {"ok": False, "error": err}
        cap = backend.open()
        if cap is None:
            return {"ok": False, "error": f"无法打开摄像头 {cam_id}"}
        try:
            if mode == "auto":
                ack = backend.set_property(cap, "auto_exposure", 0.75)
            else:
                backend.set_property(cap, "auto_exposure", 0.25)
                ack = backend.set_property(cap, "exposure", float(value)) if value is not None else True
            actual = backend.get_property(cap, "exposure")
            return {
                "ok": True,
                "camera_id": cam_id,
                "mode": mode,
                "supported": bool(ack),
                "actual_exposure": round(actual, 2) if actual is not None else None,
            }
        finally:
            backend.release(cap)

    # --- 智能拍照（场景感知 → 软件校正 → 美化） ---
    def smart_capture(
        self, cam_id: str, width: int = 640, height: int = 480,
        enhance: bool = True, jpeg_quality: int = 92,
    ) -> dict:
        """智能拍照：场景检测 → 软件校正（提亮/压暗 + 白平衡）→ 可选美化，一条龙出帧。"""
        from ..vision import auto_enhance, detect_scene, software_correct
        frame, _, err = self.capture(cam_id, width, height)
        if err:
            return {"ok": False, "error": err}
        scene = detect_scene(frame)
        frame = software_correct(frame, scene)
        post = []
        if enhance:
            frame = auto_enhance(frame)
            post = ["clahe", "sharpen"]
        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality])
        return {
            "ok": ok,
            "camera_id": cam_id,
            "scene": scene["scene"],
            "scene_confidence": scene["confidence"],
            "metrics": scene["metrics"],
            "enhancements": post,
            "jpeg_base64": "data:image/jpeg;base64," + _b64(buf.tobytes()),
        }


def _now_ms() -> float:
    import time
    return time.perf_counter() * 1000


def _b64(data: bytes) -> str:
    import base64
    return base64.b64encode(data).decode("ascii")
