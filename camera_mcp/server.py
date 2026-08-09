"""camera-mcp-server 入口：MCP server 定义与工具。

启动：camera-mcp（stdio，默认）/ camera-mcp --transport http
工具：list_cameras / capture_frame / capture_stereo / get_camera_property /
      set_camera_property / add_remote_camera / remove_remote_camera /
      auto_focus / set_exposure / smart_capture /
      detect_gestures / detect_objects / analyze_scene
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import sys
from typing import Optional

import cv2
from mcp.server import MCPServer

from camera_mcp import __version__, camera, detection, gestures, vision

logger = logging.getLogger("camera-mcp")

mcp = MCPServer(
    name="camera-vision", title="Camera Vision MCP Server",
    description="本地摄像头视觉 MCP Server：列摄像头、拍帧、双摄、属性控制、手势识别、物体检测、画面理解",
    version=__version__,
)

# CameraManager 单例（进程内共享，探测结果缓存）
manager = camera.manager


def _ok(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False)


def _jpeg_b64(jpeg: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")


def _capture_for_vision(cam_id: str, width: int, height: int):
    """拍帧用于视觉识别；返回 (frame, err)。"""
    frame, _, err = manager.capture(cam_id, width, height)
    return frame, err


@mcp.tool()
def list_cameras(refresh: bool = False) -> str:
    """列出所有可用摄像头（本地 + 远程），含分辨率与镜头类型。"""
    infos = manager.discover(refresh=refresh)
    return _ok({"cameras": [i.to_dict() for i in infos]})


@mcp.tool()
def add_remote_camera(url: str) -> str:
    """添加远程摄像头源（手机 IP Camera App 推流地址等，http/rtsp 均可）。"""
    try:
        info = manager.add_remote(url)
    except ValueError as e:
        return _ok({"ok": False, "error": str(e)})
    except Exception as e:
        return _ok({"ok": False, "error": f"添加远程摄像头失败: {e}"})
    return _ok({"ok": True, "camera": info.to_dict()})


@mcp.tool()
def remove_remote_camera(cam_id: str) -> str:
    """移除一个远程摄像头（id 形如 ip_0）。"""
    removed = manager.remove_remote(cam_id)
    if not removed:
        return _ok({"ok": False, "error": f"不是远程摄像头或不存在: {cam_id}"})
    return _ok({"ok": True, "removed": cam_id})


@mcp.tool()
def capture_frame(cam_id: str = "0", width: int = 640, height: int = 480,
                  save_to: str = "", jpeg_quality: int = 90) -> str:
    """从指定摄像头拍一帧，返回 base64 JPEG（save_to 可同时存盘）。"""
    frame, jpeg, err = manager.capture(cam_id, width, height, jpeg_quality)
    if err:
        return _ok({"ok": False, "error": err})
    h, w = frame.shape[:2]
    result: dict = {"ok": True, "width": w, "height": h, "camera_id": cam_id}
    if save_to:
        os.makedirs(os.path.dirname(os.path.abspath(save_to)), exist_ok=True)
        with open(save_to, "wb") as f:
            f.write(jpeg)
        result["image_path"] = save_to
    else:
        result["jpeg_base64"] = _jpeg_b64(jpeg)
    return _ok(result)


@mcp.tool()
def capture_stereo(
    cam1_id: str = "0",
    cam2_id: str = "ip_0",
    width: int = 640,
    height: int = 480,
) -> str:
    """两个摄像头交替读帧，返回 drift_ms / aligned 时间戳对齐报告。"""
    return _ok(manager.capture_stereo(cam1_id, cam2_id, width, height))


@mcp.tool()
def get_camera_property(cam_id: str = "0") -> str:
    """读取摄像头当前所有可调参数的值（brightness/exposure/focus 等 20 项）。"""
    return _ok(manager.get_properties(cam_id))


@mcp.tool()
def set_camera_property(cam_id: str, property: str, value: float) -> str:
    """设置摄像头参数，set 后回读，返回实际生效值。"""
    return _ok(manager.set_property(cam_id, property, value))


@mcp.tool()
def auto_focus(cam_id: str = "0", frames: int = 6,
               width: int = 640, height: int = 480) -> str:
    """自动对焦：连拍多帧取最清晰的一帧（软件模拟，不依赖硬件 focus）。"""
    return _ok(manager.auto_focus(cam_id, frames=frames, width=width, height=height))


@mcp.tool()
def set_exposure(cam_id: str, mode: str = "auto", value: Optional[float] = None) -> str:
    """曝光控制：mode=auto 自动曝光；mode=manual 切手动，value 可选。"""
    return _ok(manager.set_exposure(cam_id, mode=mode, value=value))


@mcp.tool()
def smart_capture(cam_id: str = "0", width: int = 640, height: int = 480,
                  enhance: bool = True) -> str:
    """智能拍照：场景感知 → 软件校正（提亮/压暗+白平衡）→ 可选美化，一条龙出帧。"""
    return _ok(manager.smart_capture(cam_id, width, height, enhance=enhance))


@mcp.tool()
def detect_gestures(cam_id: str = "0", width: int = 640, height: int = 480,
                    num_hands: int = 1, model_path: str = "",
                    include_image: bool = False) -> str:
    """拍一帧并做手势识别（MediaPipe HandLandmarker，7 种手势）。"""
    frame, err = _capture_for_vision(cam_id, width, height)
    if err:
        return _ok({"ok": False, "error": err})
    try:
        detector = gestures.get_detector(num_hands=num_hands)
        hands = detector.detect(frame)
    except FileNotFoundError as e:
        return _ok({"ok": False, "error": str(e)})
    except Exception as e:
        return _ok({"ok": False, "error": f"手势识别失败: {e}"})
    result = {"ok": True, "num_hands": len(hands), "hands": [h.to_dict() for h in hands]}
    if include_image:
        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
        if ok:
            result["jpeg_base64"] = _jpeg_b64(buf.tobytes())
    return _ok(result)


@mcp.tool()
def detect_objects(cam_id: str = "0", width: int = 640, height: int = 480,
                   conf: float = 0.35) -> str:
    """拍一帧并做 YOLO 物体检测（需 pip install -e ".[objects]"）。"""
    if not detection.is_available():
        return _ok({"ok": False, "error": '未安装 ultralytics，请运行 pip install -e ".[objects]"'})
    frame, err = _capture_for_vision(cam_id, width, height)
    if err:
        return _ok({"ok": False, "error": err})
    try:
        dets = detection.detect_objects(frame, conf=conf)
    except Exception as e:
        return _ok({"ok": False, "error": f"物体检测失败: {e}"})
    return _ok({"ok": True, "num_detections": len(dets), "detections": dets})


@mcp.tool()
def analyze_scene(cam_id: str = "0", width: int = 640, height: int = 480,
                  prompt: str = "请描述这张图片里发生了什么，尽量具体。") -> str:
    """拍一帧，交给本地 Ollama 视觉模型理解画面（需 Ollama + 视觉模型）。"""
    if not vision.is_available():
        return _ok({"ok": False, "error": "Ollama 未运行。请启动 Ollama 并 ollama pull qwen2.5vl"})
    frame, err = _capture_for_vision(cam_id, width, height)
    if err:
        return _ok({"ok": False, "error": err})
    try:
        desc = vision.analyze_scene(frame, prompt=prompt)
    except Exception as e:
        return _ok({"ok": False, "error": f"画面理解失败: {e}"})
    return _ok({"ok": True, "model": "qwen2.5vl", "description": desc})


def main(argv=None):
    parser = argparse.ArgumentParser(description="本地摄像头视觉 MCP Server")
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio",
                        help="MCP 传输方式（默认 stdio，http 为 streamable HTTP）")
    parser.add_argument("--host", default="127.0.0.1", help="http 模式监听地址")
    parser.add_argument("--port", type=int, default=8000, help="http 模式端口")
    parser.add_argument("-v", "--verbose", action="store_true", help="输出调试日志")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        stream=sys.stderr,  # stdio 模式下 stdout 是协议通道
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.transport == "http":
        logger.info("HTTP 模式: %s:%s", args.host, args.port)
        mcp.run(transport="streamable-http", host=args.host, port=args.port)
    else:
        logger.info("stdio 模式启动，等待 MCP 客户端连接...")
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
