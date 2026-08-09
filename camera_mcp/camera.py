"""摄像头管理：本地枚举、拍帧、双摄、远程 IP 摄像头、属性控制、场景感知与增强（内联）。"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

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

SCENES = ("dark", "normal", "overexposed")


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


# ---------------------------------------------------------------------------
# 底层工具
# ---------------------------------------------------------------------------


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


def _probe_properties(cap: cv2.VideoCapture) -> Dict[str, Dict[str, Any]]:
    """读全部候选属性当前值，读不到即不支持（简单读值版）。"""
    props = {}
    for name, prop in _PROPERTIES.items():
        v = _read_prop(cap, prop)
        props[name] = {
            "value": round(v, 2) if v is not None else None,
            "supported": v is not None,
        }
    return props


def _infer_lens_type(info: CameraInfo) -> str:
    """按最大分辨率简单推断镜头类型（启发式，仅供参考）。"""
    if info.kind == "remote" or not info.resolutions:
        return "unknown"
    max_w = max(w for w, _ in info.resolutions)
    return "wide" if max_w >= 1280 else "unknown"


# ---------------------------------------------------------------------------
# 场景感知与画面增强（内联自 scene.py / enhance.py 的核心逻辑）
# ---------------------------------------------------------------------------


def _detect_scene(frame: np.ndarray) -> dict:
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


def _clahe(img: np.ndarray, clip: float = 2.0, tile: int = 8) -> np.ndarray:
    """自适应直方图均衡：LAB 的 L 通道做，拉细节不动颜色。"""
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    l = cv2.createCLAHE(clip, (tile, tile)).apply(l)
    return cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)


def _sharpen(img: np.ndarray, amount: float = 1.5, sigma: float = 1.0) -> np.ndarray:
    """Unsharp masking：原图 + 高斯模糊层差值增强边缘。"""
    blur = cv2.GaussianBlur(img, (0, 0), sigma)
    return cv2.addWeighted(img, 1 + amount, blur, -amount, 0)


def _auto_enhance(frame: np.ndarray) -> np.ndarray:
    """一键美化：CLAHE 暗部细节 + 轻微锐化。"""
    return _sharpen(_clahe(frame))


def _software_correct(frame: np.ndarray, scene_info: dict) -> np.ndarray:
    """软件兜底校正：暗光伽马提亮 / 过曝压暗 + 灰度世界白平衡，任何摄像头都有效。"""
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


# ---------------------------------------------------------------------------
# CameraManager
# ---------------------------------------------------------------------------


class CameraManager:
    """摄像头管理：枚举 / 拍帧 / 双摄 / 远程注册 / 属性控制 / 智能拍照。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._local: Optional[List[CameraInfo]] = None
        self._remote: Dict[str, CameraInfo] = {}
        self._remote_seq = 0

    # --- 枚举与探测 ---
    def discover(self, refresh: bool = False) -> List[CameraInfo]:
        """枚举所有摄像头（本地 + 远程）；本地结果缓存，refresh 强制重探。"""
        with self._lock:
            if self._local is not None and not refresh:
                return self._local + list(self._remote.values())
            self._local = self._discover_local()
            return self._local + list(self._remote.values())

    def _discover_local(self) -> List[CameraInfo]:
        infos: List[CameraInfo] = []
        for i in range(_MAX_INDEX):
            cap = open_camera(i, retries=2)
            if cap is None:
                continue
            with cap:
                w = int(_read_prop(cap, cv2.CAP_PROP_FRAME_WIDTH) or 0)
                h = int(_read_prop(cap, cv2.CAP_PROP_FRAME_HEIGHT) or 0)
                fps = float(_read_prop(cap, cv2.CAP_PROP_FPS) or 0.0)
                backend = _backend_name(cap) or "unknown"
            if not w or not h:
                continue
            info = CameraInfo(
                id=str(i), kind="local", name=f"Camera {i}", backend=backend,
                width=w, height=h, fps=fps,
                resolutions=self._probe_resolutions(i) or [(w, h)],
            )
            info.lens_type = _infer_lens_type(info)
            infos.append(info)
        return infos

    def _probe_resolutions(self, index: int) -> List[Tuple[int, int]]:
        """独立临时 cap 探测关键候选分辨率，set 后读回实际生效值，探测完释放。"""
        cap = open_camera(index, retries=2)
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

    # --- 远程摄像头（IP Camera） ---
    def add_remote(self, url: str) -> CameraInfo:
        """注册远程视频源（IP Camera 推流地址），验证可读后登记为 ip_N。"""
        cap = cv2.VideoCapture(url)
        if not cap.isOpened():
            cap.release()
            raise ValueError(f"无法打开远程视频源: {url}")
        try:
            ret, _ = cap.read()
        except Exception:
            ret = False
        if not ret:
            cap.release()
            raise ValueError(f"远程视频源读不到帧: {url}")
        with self._lock:
            cam_id = f"ip_{self._remote_seq}"
            self._remote_seq += 1
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
            info = CameraInfo(
                id=cam_id, kind="remote", name=url, backend="MJPEG-http",
                width=w, height=h,
                fps=float(cap.get(cv2.CAP_PROP_FPS) or 0.0),
                resolutions=[(w, h)],
            )
            self._remote[cam_id] = info
        cap.release()
        return info

    def remove_remote(self, cam_id: str) -> bool:
        with self._lock:
            if cam_id in self._remote:
                del self._remote[cam_id]
                return True
        return False

    # --- 拍帧 ---
    def _resolve(self, cam_id: str) -> Tuple[Optional[CameraInfo], str]:
        """把 cam_id 解析成摄像头信息：'0' → 本地 index；'ip_0' → 远程。"""
        with self._lock:
            if cam_id in self._remote:
                return self._remote[cam_id], ""
        if cam_id.isdigit():
            for info in self.discover():
                if info.kind == "local" and info.id == cam_id:
                    return info, ""
            return None, f"本地摄像头 index={cam_id} 未探测到"
        return None, f"未知摄像头 id: {cam_id}（可用 list_cameras 查看）"

    def _open(self, info: CameraInfo, width: int = 640, height: int = 480):
        if info.kind == "local":
            return open_camera(int(info.id), width, height)
        return cv2.VideoCapture(info.name)  # 远程：name 即 URL

    def capture(
        self, cam_id: str, width: int = 640, height: int = 480, jpeg_quality: int = 90
    ) -> Tuple[Optional[np.ndarray], Optional[bytes], Optional[str]]:
        """按 cam_id 拍一帧，返回 (BGR 帧, JPEG bytes, error)。用完即释放。"""
        info, err = self._resolve(cam_id)
        if info is None:
            return None, None, err
        cap = self._open(info, width, height)
        if cap is None or not cap.isOpened():
            return None, None, f"无法打开摄像头 {cam_id}"
        try:
            ret, frame = cap.read()
            if not ret or frame is None:
                return None, None, f"摄像头 {cam_id} 读取帧失败"
            ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality])
            if not ok:
                return None, None, "JPEG 编码失败"
            return frame, buf.tobytes(), None
        finally:
            cap.release()

    def capture_stereo(
        self,
        cam1_id: str,
        cam2_id: str,
        width: int = 640,
        height: int = 480,
        jpeg_quality: int = 85,
    ) -> dict:
        """两路交替读帧（Windows 后端非线程安全，串行间隔最小），返回对齐报告。"""
        info1, e1 = self._resolve(cam1_id)
        info2, e2 = self._resolve(cam2_id)
        if info1 is None or info2 is None:
            return {"ok": False, "error": e1 or e2}
        cap1 = self._open(info1, width, height)
        cap2 = self._open(info2, width, height)
        if cap1 is None or cap2 is None or not cap1.isOpened() or not cap2.isOpened():
            for c in (cap1, cap2):
                if c is not None:
                    c.release()
            return {"ok": False, "error": "至少一路摄像头无法打开"}
        try:
            cap1.read()
            cap2.read()
            r1, fr1 = cap1.read()
            t1 = time.perf_counter() * 1000
            r2, fr2 = cap2.read()
            t2 = time.perf_counter() * 1000
            frames = []
            for cam_id, ret, frame, t in ((cam1_id, r1, fr1, t1), (cam2_id, r2, fr2, t2)):
                if not ret or frame is None:
                    continue
                ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality])
                if ok:
                    import base64
                    b64 = base64.b64encode(buf.tobytes()).decode("ascii")
                    frames.append({"camera_id": cam_id, "t_ms": round(t, 2),
                                   "jpeg_base64": "data:image/jpeg;base64," + b64})
            drift_ms = abs(t2 - t1)
            return {
                "ok": len(frames) == 2,
                "frames": frames,
                "drift_ms": round(drift_ms, 2),
                "aligned": drift_ms <= 50.0,
            }
        finally:
            cap1.release()
            cap2.release()

    # --- 属性控制 ---
    def get_properties(self, cam_id: str) -> dict:
        """返回摄像头当前所有可调属性的值（读不到即不支持）。"""
        info, err = self._resolve(cam_id)
        if info is None:
            return {"ok": False, "error": err}
        cap = self._open(info)
        if cap is None or not cap.isOpened():
            return {"ok": False, "error": f"无法打开摄像头 {cam_id}"}
        try:
            return {"ok": True, "camera_id": cam_id, "properties": _probe_properties(cap)}
        finally:
            cap.release()

    def set_property(self, cam_id: str, prop_name: str, value: float) -> dict:
        """设置摄像头属性，set 后回读，返回实际生效值。"""
        if prop_name not in _PROPERTIES:
            return {"ok": False, "error": f"未知属性 {prop_name}。可用: {list(_PROPERTIES)}"}
        info, err = self._resolve(cam_id)
        if info is None:
            return {"ok": False, "error": err}
        cap = self._open(info)
        if cap is None or not cap.isOpened():
            return {"ok": False, "error": f"无法打开摄像头 {cam_id}"}
        try:
            prop = _PROPERTIES[prop_name]
            ok_set = cap.set(prop, float(value))
            actual = _read_prop(cap, prop)
            return {
                "ok": True,
                "camera_id": cam_id,
                "property": prop_name,
                "requested": value,
                "set_ack": bool(ok_set),
                "actual_value": round(actual, 2) if actual is not None else None,
            }
        finally:
            cap.release()

    # --- 对焦 / 曝光（软件级，尽力而为） ---
    def auto_focus(self, cam_id: str, frames: int = 6, width: int = 640, height: int = 480) -> dict:
        """连拍 N 帧取 Laplacian 方差最高的一帧（软件模拟对焦）。"""
        info, err = self._resolve(cam_id)
        if err:
            return {"ok": False, "error": err}
        cap = self._open(info, width, height)
        if cap is None or not cap.isOpened():
            return {"ok": False, "error": f"无法打开摄像头 {cam_id}"}
        try:
            best, best_score, best_i = None, -1.0, -1
            for i in range(frames):
                ret, frame = cap.read()
                if ret and frame is not None:
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    s = float(cv2.Laplacian(gray, cv2.CV_64F).var())
                    if s > best_score:
                        best, best_score, best_i = frame, s, i
                time.sleep(0.05)
        finally:
            cap.release()
        if best is None:
            return {"ok": False, "error": "连拍失败，无法对焦"}
        ok, buf = cv2.imencode(".jpg", best, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
        import base64
        return {
            "ok": True,
            "camera_id": cam_id,
            "sharpness": round(best_score, 1),
            "frame_index": best_i,
            "jpeg_base64": "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode("ascii"),
        }

    def set_exposure(self, cam_id: str, mode: str = "auto", value: Optional[float] = None) -> dict:
        """曝光控制：mode=auto 自动曝光；mode=manual 切手动，value 可选。"""
        if mode not in ("auto", "manual"):
            return {"ok": False, "error": f"mode 必须为 auto/manual，收到 {mode}"}
        info, err = self._resolve(cam_id)
        if err:
            return {"ok": False, "error": err}
        cap = self._open(info)
        if cap is None or not cap.isOpened():
            return {"ok": False, "error": f"无法打开摄像头 {cam_id}"}
        try:
            if mode == "auto":
                ack = cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.75)
            else:
                cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)
                ack = cap.set(cv2.CAP_PROP_EXPOSURE, float(value)) if value is not None else True
            actual = _read_prop(cap, cv2.CAP_PROP_EXPOSURE)
            return {
                "ok": True,
                "camera_id": cam_id,
                "mode": mode,
                "supported": bool(ack),
                "actual_exposure": round(actual, 2) if actual is not None else None,
            }
        finally:
            cap.release()

    # --- 智能拍照（场景感知 → 软件校正 → 美化） ---
    def smart_capture(
        self, cam_id: str, width: int = 640, height: int = 480,
        enhance: bool = True, jpeg_quality: int = 92,
    ) -> dict:
        """智能拍照：场景检测 → 软件校正（提亮/压暗 + 白平衡）→ 可选美化，一条龙出帧。"""
        frame, _, err = self.capture(cam_id, width, height)
        if err:
            return {"ok": False, "error": err}
        scene = _detect_scene(frame)
        frame = _software_correct(frame, scene)
        post = []
        if enhance:
            frame = _auto_enhance(frame)
            post = ["clahe", "sharpen"]
        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality])
        import base64
        return {
            "ok": ok,
            "camera_id": cam_id,
            "scene": scene["scene"],
            "scene_confidence": scene["confidence"],
            "metrics": scene["metrics"],
            "enhancements": post,
            "jpeg_base64": "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode("ascii"),
        }


# 进程级单例（探测结果缓存，进程内共享）
manager = CameraManager()
