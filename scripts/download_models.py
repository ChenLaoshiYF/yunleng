"""下载 MediaPipe hand_landmarker 模型到项目 models/ 目录。

用法:
    python scripts/download_models.py

模型:
    hand_landmarker.task  手势关键点（MediaPipe 官方 float16 版）
    （YOLO 模型不需要手动下载，ultralytics 首次运行时自动拉取）
"""

from __future__ import annotations

import os
import urllib.request

MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")

# MediaPipe 官方模型仓库
HAND_LANDMARKER_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
)


def download(url: str, dest: str) -> None:
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.isfile(dest):
        print(f"[跳过] {dest} 已存在")
        return
    print(f"[下载] {url}")
    urllib.request.urlretrieve(url, dest)
    size_mb = os.path.getsize(dest) / 1024 / 1024
    print(f"[完成] {dest} ({size_mb:.1f} MB)")


def main():
    download(HAND_LANDMARKER_URL, os.path.join(MODELS_DIR, "hand_landmarker.task"))
    print("\n模型就绪。启动 server 时可用环境变量覆盖：")
    print("  CAMERA_MCP_HAND_MODEL  手势模型路径")
    print("  CAMERA_MCP_YOLO_MODEL  YOLO 权重（如 yolov8s.pt）")
    print("  CAMERA_MCP_OLLAMA_MODEL Ollama 视觉模型名")


if __name__ == "__main__":
    main()
