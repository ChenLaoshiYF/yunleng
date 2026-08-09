# 云棱 · Yunleng

> 来自西工大电子信息 Mr.chen，给 AI Agent 装上眼睛。

对着摄像头比个手势，Agent 知道你在比心还是握拳。手机装个 IP 摄像头 App 连上 WiFi，Agent 就能同时看到你的电脑摄像头和手机画面。没有黑魔法，就是一个跑在本地的 MCP Server，把摄像头变成 AI 能调用的工具。

## 它能干什么

- **多摄像头管理**：自动发现本地所有摄像头 + 远程 IP Camera，区分分辨率、帧率、镜头类型
- **拍帧 / 双摄并发**：单帧拍照，或两路摄像头同时拉画面，带时间戳对齐
- **属性控制**：亮度、对比度、曝光、白平衡、对焦等 20 项参数，设置后回读确认
- **智能拍照**：暗光自动提亮、过曝自动压低、白平衡校正，一条龙出片
- **手势识别**：MediaPipe 直接跑的，张手、握拳、竖拇指、剪刀手、OK、比心、比一，七种手势
- **物体检测**：YOLO（可选装上就能用）
- **画面理解**：接本地 Ollama 视觉模型，拍一帧 AI 直接告诉你画面里有什么

## 为什么做这个

MCP 生态里浏览器、数据库、文件系统的工具一堆，但**摄像头/视觉感知几乎没人碰**。你手机上有三颗镜头，AI Agent 一颗都用不了。这个项目就是填这个坑的。

## 安装

```bash
git clone https://github.com/ChenLaoshiYF/yunleng.git
cd yunleng
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -e .
python scripts/download_models.py
```

可选：

```bash
pip install -e ".[objects]"   # YOLO 物体检测
```

## 连接到你的 Agent

Claude Desktop 为例，在 `claude_desktop_config.json` 加：

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

然后对 Agent 说「看看摄像头里有什么」「识别一下我的手势」「帮我拍张照」。

## 接手机摄像头

手机装个 IP Webcam App，WiFi 下开启推流，把地址喂给 Agent：`add_remote_camera url="http://192.168.x.x:8080/video"`。完事。

## 工具一览

13 个工具：`list_cameras`、`capture_frame`、`capture_stereo`、`get/set_camera_property`、`smart_capture`、`auto_focus`、`set_exposure`、`add/remove_remote_camera`、`detect_gestures`、`detect_objects`、`analyze_scene`

## 验证

- smoke_test 3 遍全过
- 5 分钟连续拍照稳定测试：10 帧零失败零 crash，内存平稳
- 100 次连续 capture 无衰减

## 依赖

`mcp` · `opencv-python` · `numpy` · `mediapipe`，就四个。

## License

MIT
