"""Mock IP 摄像头：本地模拟手机 IP Camera App 的 MJPEG 推流 + /info.json。

用途：没有真机时验证远程摄像头链路（add_remote_camera → capture → stereo）。

两种帧来源：
- --pattern：生成动态测试图案（不依赖摄像头，最稳定，适合 CI/自动化）
- --source N：用本地摄像头 index N 的真实画面推流

既可独立运行：
    python scripts/mock_ip_camera.py --port 8080 --pattern

也可被 smoke_test import 复用（start_mock 起后台线程）：
    from mock_ip_camera import start_mock
    url, stop = start_mock(port=0)   # port=0 自动分配空闲端口
"""

from __future__ import annotations

import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2
import numpy as np

BOUNDARY = "mockframe"


def _make_pattern_frame(t: float, w: int = 640, h: int = 480) -> np.ndarray:
    """生成带时间戳文字的彩色测试帧，模拟"活的"摄像头画面。"""
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    # 渐变底色
    gradient = np.linspace(0, 200, w, dtype=np.uint8)
    frame[:, :, 0] = gradient[np.newaxis, :]  # 蓝渐变
    frame[:, :, 2] = 255 - gradient[np.newaxis, :]
    # 中心色块（随秒变动）
    sec = int(t) % 8
    color = [(0, 0, 255), (0, 255, 0), (255, 0, 0), (0, 255, 255),
             (255, 0, 255), (255, 255, 0), (128, 128, 255), (255, 128, 128)][sec]
    cv2.rectangle(frame, (w // 4, h // 4), (3 * w // 4, 3 * h // 4), color, -1)
    # 时间戳文字
    label = time.strftime("mock %H:%M:%S", time.localtime(t))
    cv2.putText(frame, label, (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.2,
                (255, 255, 255), 2, cv2.LINE_AA)
    return frame


class MockCameraHandler(BaseHTTPRequestHandler):
    source: int = -1          # -1 = pattern 模式
    cap: cv2.VideoCapture | None = None
    quality: int = 70

    def log_message(self, fmt, *args):  # 静默访问日志
        pass

    def do_GET(self):
        if self.path.startswith("/info.json"):
            self._serve_info()
        elif self.path.startswith("/video"):
            self._serve_mjpeg()
        else:
            self.send_response(404)
            self.end_headers()

    def _serve_info(self):
        """模拟手机 IP Webcam App 的 /info.json 元数据接口。"""
        body = json.dumps({
            "cur_res": "640x480",
            "pref_quality": "medium",
            "battery": 82,
            "orientation": 0,
            "mock": True,
        }).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_mjpeg(self):
        """输出 multipart/x-mixed-replace MJPEG 流（IP Camera App 的标准推流格式）。"""
        self.send_response(200)
        self.send_header("Content-Type", f"multipart/x-mixed-replace; boundary={BOUNDARY}")
        self.end_headers()

        if self.source >= 0:
            if MockCameraHandler.cap is None or not MockCameraHandler.cap.isOpened():
                MockCameraHandler.cap = cv2.VideoCapture(self.source)
            read = lambda: MockCameraHandler.cap.read()  # noqa: E731
        else:
            read = lambda: (True, _make_pattern_frame(time.time()))  # noqa: E731

        try:
            while True:
                ret, frame = read()
                if not ret or frame is None:
                    time.sleep(0.1)
                    continue
                ok, buf = cv2.imencode(
                    ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), self.quality]
                )
                if not ok:
                    continue
                data = buf.tobytes()
                self.wfile.write(f"--{BOUNDARY}\r\n".encode("ascii"))
                self.wfile.write(b"Content-Type: image/jpeg\r\n")
                self.wfile.write(f"Content-Length: {len(data)}\r\n\r\n".encode("ascii"))
                self.wfile.write(data)
                self.wfile.write(b"\r\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass  # 客户端断开，正常结束


class MockIPCamera:
    """后台线程运行的 mock 摄像头服务器。"""

    def __init__(self, port: int = 0, source: int = -1, quality: int = 70):
        MockCameraHandler.source = source
        MockCameraHandler.quality = quality
        self._server = ThreadingHTTPServer(("127.0.0.1", port), MockCameraHandler)
        self.port = self._server.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}/video"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def start(self):
        self._thread.start()
        return self

    def stop(self):
        self._server.shutdown()
        self._server.server_close()
        if MockCameraHandler.cap is not None:
            MockCameraHandler.cap.release()
            MockCameraHandler.cap = None

    def __enter__(self):
        return self.start()

    def __exit__(self, *args):
        self.stop()


def start_mock(port: int = 0, source: int = -1) -> tuple[str, MockIPCamera]:
    """便捷入口：起一个 mock 摄像头，返回 (视频流 URL, 服务对象)。"""
    mock = MockIPCamera(port=port, source=source).start()
    return mock.url, mock


def main():
    parser = argparse.ArgumentParser(description="Mock IP 摄像头（MJPEG 推流）")
    parser.add_argument("--port", type=int, default=8080, help="监听端口")
    parser.add_argument("--pattern", action="store_true",
                        help="用生成的测试图案（默认，不依赖摄像头）")
    parser.add_argument("--source", type=int, default=-1,
                        help="用本地摄像头 index 推真实画面（与 --pattern 二选一）")
    args = parser.parse_args()

    src = args.source if not args.pattern and args.source >= 0 else -1
    mock = MockIPCamera(port=args.port, source=src).start()
    print(f"mock IP camera 已启动: {mock.url}")
    print(f"元数据接口: http://127.0.0.1:{mock.port}/info.json")
    print("按 Ctrl+C 停止")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        mock.stop()
        print("\n已停止")


if __name__ == "__main__":
    main()
