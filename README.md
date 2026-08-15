# 👁️ Yunleng — Give Your AI Agent Eyes

**云棱** · A local MCP server that turns your cameras into tools your AI can call.

Your agent can read ten thousand files in a minute. It can browse the whole internet, write a novel, debug a kernel, beat you at chess. But right now, it has **no idea what your face looks like**.

Yunleng fixes that. Point your laptop camera at yourself and wave — your agent sees it. Set your phone on a tripod facing your desk and your agent watches both angles at once. No cloud, no black box, no API keys. Just a Python process on your machine that hands your AI a pair of eyes.

---

> Built by a student at Northwestern Polytechnical University (西工大) who got tired of AI agents being blind.

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB)
![MCP](https://img.shields.io/badge/MCP-Server-7B3FF2)
![License](https://img.shields.io/badge/License-MIT-green)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey)

---

## Why this exists

The MCP ecosystem has servers for browsers, databases, file systems, git, Slack, you name it. A whole economy of tools that let AI *touch* the world.

Almost nobody built one for **seeing** it.

Your phone has three lenses. Your laptop has a webcam. Your AI agent can use exactly zero of them. That gap is what this project fills — a first-class, local-first vision channel for agents, with no cloud round-trip.

## What it can do

**👀 See multiple cameras at once.** Auto-discovers every camera on your machine, and you can add your phone as a second angle over WiFi (IP Webcam / RTSP). Stereo capture with millisecond-aligned timestamps — your agent watches two sides of the room simultaneously.

**🎛️ Fine-tune the shot.** 20 camera properties exposed: brightness, contrast, exposure, white balance, focus, zoom, and more. Every set is read back and confirmed — no silent failures, no "trust me it worked".

**🌙 Take smart photos.** Dark scene? It brightens. Overexposed? It pulls it down. White balance corrected before you even finish the sentence. One call, a decent photo comes out the other end.

**✋ Read your hands.** MediaPipe underneath, seven gestures: open palm, fist, thumbs up, peace, OK, heart, and the one-finger "1". Rule-based and fully interpretable — no training, no black box, every decision traceable to a geometry check.

**🎯 Detect objects (optional).** YOLO, install-on-demand. Defaults to `yolov8n` and swaps to your own weights with one env var.

**🧠 Understand the scene.** Hand a frame to your local Ollama vision model (`qwen2.5vl`) and get back a plain-language description. Fully offline, fully private.

## Install

```bash
git clone https://github.com/ChenLaoshiYF/yunleng.git
cd yunleng
python -m venv .venv
.venv\Scripts\activate      # Windows (macOS/Linux: source .venv/bin/activate)
pip install -e .
python scripts/download_models.py
```

That's it — four dependencies: `mcp`, `opencv-python`, `numpy`, `mediapipe`.

Optional YOLO object detection:

```bash
pip install -e ".[objects]"
```

## Connect to your agent

Claude Desktop example — add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "camera-vision": {
      "command": "/absolute/path/to/your/.venv/Scripts/python.exe",
      "args": ["-m", "camera_mcp.server"],
      "cwd": "/absolute/path/to/yunleng"
    }
  }
}
```

Then just talk to your agent:

> *"Look at the camera and tell me what you see."*
>
> *"What gesture am I making?"*
>
> *"Take a photo and save it."*

## Use your phone as a second eye

Install any IP Webcam app on your phone, join the same WiFi as your computer, start streaming, then hand the URL to your agent:

```
add_remote_camera url="http://192.168.x.x:8080/video"
```

Done. Your laptop's blind spot is now covered.

## Scene understanding (optional)

`analyze_scene` needs a local Ollama with a vision model:

1. Install Ollama: https://ollama.com
2. Pull a vision model: `ollama pull qwen2.5vl`

If Ollama isn't running, that one tool returns a clear error message. Everything else keeps working.

## Configuration (env vars)

| Variable | What it does | Default |
|----------|-------------|---------|
| `CAMERA_MCP_HAND_MODEL` | Path to the hand-landmark model | project `models/` dir |
| `CAMERA_MCP_YOLO_MODEL` | Path to a YOLO weights file | `yolov8n.pt` |
| `CAMERA_MCP_OLLAMA_MODEL` | Ollama vision model name | `qwen2.5vl` |
| `CAMERA_MCP_OLLAMA_URL` | Ollama server address | `http://localhost:11434` |

## The 13 tools

| Tool | What it does |
|------|-------------|
| `list_cameras` | List every camera (local + remote) |
| `capture_frame` | Grab one frame, return base64 JPEG |
| `capture_stereo` | Two cameras at once, timestamps aligned |
| `get_camera_property` | Read all 20 adjustable parameters |
| `set_camera_property` | Set a parameter, read back the actual value |
| `smart_capture` | Scene-aware photo (auto brightness + white balance) |
| `auto_focus` | Software autofocus — picks the sharpest frame |
| `set_exposure` | Auto / manual exposure control |
| `add_remote_camera` | Register a phone / IP camera |
| `remove_remote_camera` | Remove a remote camera |
| `detect_gestures` | Seven-gesture recognition |
| `detect_objects` | YOLO object detection (optional) |
| `analyze_scene` | Describe the frame via local Ollama |

## Design choices worth knowing

- **Cameras are opened per-call and released immediately.** No lingering handles, no resource leaks on marathon sessions.
- **Models load once, shared process-wide.** The first call is slow, everything after is fast.
- **Graceful degradation everywhere.** No Ollama? No YOLO? Those tools tell you clearly instead of crashing the server.
- **Layered architecture (v0.2.0).** `camera/` abstracts backends (local/remote) behind a single interface; `vision/` owns scene detection + enhancement + VLM understanding. The MCP layer stays thin and stable on top.

## Battle-tested

Smoke tests run against a live server over real MCP — 16/16 checks green:

- Handshake, all 13 tools registered ✔
- Camera enumeration + property read/write ✔
- Remote camera add/remove + frame capture ✔
- Stereo capture with **~1ms drift**, timestamps aligned ✔
- Smart capture, autofocus, exposure ✔
- Scene understanding degrades gracefully without Ollama ✔

Long-run stability: 10/10 frames over 300s, zero failures, flat memory.

The full suite is in `scripts/` — `smoke_test.py`, `stability_check.py`, `long_run_test.py`. Don't take my word for it; run them yourself.

---

## Related projects

Part of the [ChenLaoshiYF](https://github.com/ChenLaoshiYF) open-source family:

- [**mcpguard 明棱**](https://github.com/ChenLaoshiYF/mcpguard) — AI agent security scanner: detects prompt injection, tool poisoning and hidden instructions in MCP servers and skills
- [**chening 陈棱**](https://github.com/ChenLaoshiYF/chening) — CUMCM math modeling AI skill pack for Chinese national contest students
- [**zhiyin 纸音**](https://github.com/ChenLaoshiYF/zhiyin) — real-time Russian→Chinese interpretation for online classes

---

## License

MIT

---

*Yunleng — 云棱, the cloud's edge. The place where AI finally starts looking at the world.*

*Star it if you want your agents to see too.* ⭐
