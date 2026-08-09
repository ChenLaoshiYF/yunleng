# 云棱 · Yunleng

摄像头视觉 MCP Server。装进 AI Agent，它就能调用你电脑和手机上的摄像头：拍帧、调参数、识别手势、做物体检测、让本地大模型描述画面里有什么。

> 来自西工大电子信息 Mr.chen

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB)
![MCP](https://img.shields.io/badge/MCP-Server-7B3FF2)
![License](https://img.shields.io/badge/License-MIT-green)

---

## 这个项目解决什么问题

MCP 生态里，浏览器、数据库、文件系统都有对应的工具，唯独摄像头没什么人做。你的 AI Agent 能读文件、能查网页，但看不见你面前的画面。

这个项目补上这一块：把摄像头变成 MCP 工具，Agent 可以自己拍照、自己看、自己判断。

## 功能

- **多摄像头**：自动发现本地摄像头，也能添加手机 IP 摄像头，支持双路同时取帧（时间戳对齐）
- **参数控制**：亮度、对比度、曝光、白平衡、对焦等 20 项参数，设置后会回读确认实际生效值
- **智能拍照**：暗光自动提亮、过曝自动压低、白平衡校正，一条命令出片
- **手势识别**：基于 MediaPipe，识别张手、握拳、竖拇指、剪刀手、OK、比心、比一七种手势
- **物体检测**：可选装 YOLO，检测画面里的物体
- **画面理解**：拍一帧交给本地 Ollama 视觉模型（默认 qwen2.5vl），返回对画面的文字描述

## 安装

```bash
git clone https://github.com/ChenLaoshiYF/yunleng.git
cd yunleng
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -e .
python scripts/download_models.py
```

只需要四个依赖：`mcp`、`opencv-python`、`numpy`、`mediapipe`。

可选装 YOLO 物体检测：

```bash
pip install -e ".[objects]"
```

## 连接到你的 Agent

以 Claude Desktop 为例，编辑 `claude_desktop_config.json`：

```json
{
  "mcpServers": {
    "camera-vision": {
      "command": "你本地的 .venv\\Scripts\\python.exe",
      "args": ["-m", "camera_mcp.server"],
      "cwd": "你 clone 的 yunleng 目录"
    }
  }
}
```

之后可以直接对 Agent 说「看看摄像头里有什么」「识别一下我的手势」「帮我拍张照」。

## 接手机摄像头

手机装 IP Webcam 之类的 App，和电脑连同一 WiFi，开启推流，然后把地址告诉 Agent：

```
add_remote_camera url="http://192.168.x.x:8080/video"
```

## 工具一览

共 13 个工具：

| 工具 | 作用 |
|------|------|
| `list_cameras` | 列出所有摄像头（本地 + 远程） |
| `capture_frame` | 拍一帧，返回 base64 JPEG |
| `capture_stereo` | 双摄像头同时取帧，时间戳对齐 |
| `get_camera_property` | 读取当前所有可调参数 |
| `set_camera_property` | 设置参数并回读确认 |
| `smart_capture` | 智能拍照（自动校正明暗和白平衡） |
| `auto_focus` | 软件自动对焦 |
| `set_exposure` | 曝光控制 |
| `add_remote_camera` | 添加远程/手机摄像头 |
| `remove_remote_camera` | 移除远程摄像头 |
| `detect_gestures` | 七种手势识别 |
| `detect_objects` | YOLO 物体检测（可选） |
| `analyze_scene` | 用本地 Ollama 描述画面 |

## 测试情况

- smoke test 3 遍通过
- 5 分钟连续拍照稳定性测试：10 帧零失败，内存平稳
- 100 次连续 capture 无衰减

## License

MIT
