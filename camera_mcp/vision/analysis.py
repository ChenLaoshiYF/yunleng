"""画面理解模块：通过本地 Ollama 调用 Qwen-VL（或其他 VLM）理解画面。

纯 HTTP 调用 Ollama 的 /api/generate，不需要额外 Python 依赖；
Ollama 未启动或模型未拉取时返回清晰提示，不影响 server 主流程。

要求：
- 本机已装 Ollama（https://ollama.com）
- 已拉取视觉模型：ollama pull qwen2.5vl  （或其他支持图片的模型）
"""

from __future__ import annotations

import base64
import json
import os
import urllib.request

import numpy as np

DEFAULT_MODEL = "qwen2.5vl"
DEFAULT_URL = "http://localhost:11434"


def is_available() -> bool:
    """检查 Ollama 服务是否在运行。"""
    url = os.environ.get("CAMERA_MCP_OLLAMA_URL", DEFAULT_URL)
    try:
        with urllib.request.urlopen(f"{url}/api/tags", timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


def analyze_scene(
    frame_bgr: np.ndarray,
    prompt: str = "请描述这张图片里发生了什么。",
    model: str = "",
    url: str = "",
    jpeg_quality: int = 80,
) -> str:
    """将帧发给本地 VLM，返回文字描述。

    参数可通过环境变量覆盖：CAMERA_MCP_OLLAMA_MODEL / CAMERA_MCP_OLLAMA_URL
    """
    model = model or os.environ.get("CAMERA_MCP_OLLAMA_MODEL", DEFAULT_MODEL)
    url = url or os.environ.get("CAMERA_MCP_OLLAMA_URL", DEFAULT_URL)

    import cv2  # 局部导入，避免依赖链

    ok, buf = cv2.imencode(
        ".jpg", frame_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality]
    )
    if not ok:
        return "[错误] 图片编码失败"
    image_b64 = base64.b64encode(buf.tobytes()).decode("ascii")

    payload = {
        "model": model,
        "prompt": prompt,
        "images": [image_b64],
        "stream": False,
    }
    req = urllib.request.Request(
        f"{url}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("response", "").strip() or "[无输出]"
    except urllib.error.URLError as e:
        return (
            f"[错误] 无法连接 Ollama（{url}）：{e.reason}。"
            "请确认 Ollama 已启动，且已 `ollama pull qwen2.5vl`。"
        )
