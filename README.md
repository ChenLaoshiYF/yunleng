<div align="center">

# 👁️ 云棱 · Yunleng

### 给 AI Agent 装上眼睛

> **摄像头视觉 MCP Server** —— 对着摄像头比个手势，AI 知道你在比心还是握拳；手机连上 WiFi，AI 同时看得见你的电脑摄像头和手机画面。没有黑魔法，就是一个跑在本地的工具，把摄像头变成 AI 能动用的能力。

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![MCP](https://img.shields.io/badge/MCP-Server-7B3FF2)
![License](https://img.shields.io/badge/License-MIT-green)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)

*来自西工大电子信息 Mr.chen*

</div>

---

## 🧠 一句话说我做什么

**MCP 生态里浏览器、数据库、文件系统的工具一堆，唯独"摄像头 / 视觉感知"几乎没人碰。你手机上有三颗镜头，AI Agent 一颗都用不上。** 这个项目就是来填这个坑的 —— 让 AI 第一次真正"看见"你的世界。

---

## ✨ 它能干什么

### 📷 多摄像头管理
自动发现本地所有摄像头 + 远程 IP Camera，区分分辨率、帧率、镜头类型。电脑拍不到的角度，手机顶上。

### 🎞️ 拍帧 / 双摄并发
单帧拍照，或两路摄像头同时拉画面，带时间戳对齐 —— 双视角一次搞定。

### 🎛️ 属性控制
亮度、对比度、曝光、白平衡、对焦等 **20 项参数**，设置后回读确认，绝不瞎改。

### 🌙 智能拍照
暗光自动提亮、过曝自动压低、白平衡校正，一条龙出片。

### ✋ 手势识别
MediaPipe 直接跑，**张手、握拳、竖拇指、剪刀手、OK、比心、比一**，七种手势实时识别。

### 🎯 物体检测
YOLO 可选装上就能用，认出画面里有什么东西。

### 🧠 画面理解
接本地 Ollama 视觉模型，拍一帧，AI 直接告诉你画面里发生了什么。

---

## 🚀 快速开始

```bash
git clone https://github.com/ChenLaoshiYF/yunleng.git
cd yunleng
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -e .
python scripts/download_models.py
```

> 只要四个依赖：`mcp` · `opencv-python` · `numpy` · `mediapipe`

YOLO 物体检测是可选项：

```bash
pip install -e ".[objects]"   # 可选
```

---

## 🔌 连接到你的 Agent

以 Claude Desktop 为例，在 `claude_desktop_config.json` 加：

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

然后对 Agent 说：
- 👋 「**看看摄像头里有什么**」
- ✋ 「**识别一下我的手势**」
- 📸 「**帮我拍张照**」

---

## 📱 接手机摄像头

手机装个 **IP Webcam App**，连上同一个 WiFi 开推流，把地址喂给 AI：

```
add_remote_camera url="http://192.168.x.x:8080/video"
```

完事，电脑摄像头看不到的角度，交给手机。

---

## 🧰 工具一览

13 个开箱即用的工具：

| 工具 | 干嘛的 |
|------|--------|
| `list_cameras` | 列出所有摄像头（本地 + 远程） |
| `capture_frame` | 拍一帧，返回 base64 JPEG |
| `capture_stereo` | 双摄并发，时间戳对齐 |
| `get_camera_property` | 读 20 项参数 |
| `set_camera_property` | 设置参数并回读确认 |
| `smart_capture` | 智能拍照一条龙 |
| `auto_focus` | 软件自动对焦 |
| `set_exposure` | 曝光控制 |
| `add_remote_camera` | 加手机/远程摄像头 |
| `remove_remote_camera` | 移除远程摄像头 |
| `detect_gestures` | 七种手势识别 |
| `detect_objects` | YOLO 物体检测（可选） |
| `analyze_scene` | Ollama 画面理解 |

---

## ✅ 扛过检验

- smoke_test **3 遍全过**
- 5 分钟连续拍照稳定测试：**10 帧零失败零 crash**，内存平稳
- 100 次连续 capture **无衰减**

---

## 📄 License

MIT

---

*给 AI 装上一双眼睛，让它开始真正看着你说话。*
