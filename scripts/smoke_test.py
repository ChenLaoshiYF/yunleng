"""冒烟测试：以 MCP 客户端身份连接本地 server，验证核心链路。

用法:
    python scripts/smoke_test.py                 # 核心链路（枚举/属性/远程/双摄/拍帧）
    python scripts/smoke_test.py --gestures      # 追加手势识别链路
    python scripts/smoke_test.py --objects       # 追加 YOLO 检测链路（需装 [objects]）

覆盖：握手 → 列工具 → 枚举 → 属性读写 → mock 远程接入 → 远程拍帧 →
      双摄并发（时间戳对齐）→ 智能拍照 / 对焦 / 曝光 →（可选）手势 / 物体 / 画面理解
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

from mcp import ClientSession, StdioServerParameters, stdio_client

# 项目根（scripts/ 的上级），保证能 import mock_ip_camera
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from mock_ip_camera import start_mock  # noqa: E402

PASS = 0
FAIL = 0


def check(name: str, cond: bool, detail: str = ""):
    global PASS, FAIL
    mark = "✔" if cond else "✘"
    if cond:
        PASS += 1
    else:
        FAIL += 1
    print(f"  [{mark}] {name}" + (f"  {detail}" if detail else ""))


async def call(session: ClientSession, tool: str, args: dict) -> dict:
    r = await session.call_tool(tool, args)
    return json.loads(r.content[0].text)


async def main(with_gestures: bool, with_objects: bool):
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "camera_mcp.server"], cwd=ROOT
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("[1/8] MCP 握手成功")

            tools = await session.list_tools()
            names = [t.name for t in tools.tools]
            print(f"[2/8] 工具列表 ({len(names)}): {names}")
            expected = {
                "list_cameras", "capture_frame", "capture_stereo",
                "get_camera_property", "set_camera_property",
                "add_remote_camera", "remove_remote_camera",
                "auto_focus", "set_exposure", "smart_capture",
                "detect_gestures", "detect_objects", "analyze_scene",
            }
            missing = expected - set(names)
            check("13 个工具全部注册", not missing, f"缺少: {missing}")

            # ----------------------------------------------------------
            # 3. 摄像头枚举
            # ----------------------------------------------------------
            print("[3/8] 摄像头枚举")
            data = await call(session, "list_cameras", {"refresh": True})
            cams = data.get("cameras", [])
            check("枚举到摄像头", len(cams) > 0, f"{len(cams)} 个")

            local = [c for c in cams if c["kind"] == "local"]
            local_id = local[0]["id"] if local else "0"
            check("本地摄像头字段齐全", all(
                c.get("id") is not None and c.get("resolutions")
                and c.get("lens_type") in (
                    "wide", "ultrawide", "telephoto", "macro", "depth", "unknown")
                for c in local
            ), "id/resolutions/lens_type 字段齐全")

            # ----------------------------------------------------------
            # 4. 属性读写
            # ----------------------------------------------------------
            print("[4/8] 属性读写")
            if local:
                cam_id = local[0]["id"]
                gp = await call(session, "get_camera_property", {"cam_id": cam_id})
                check("get_camera_property 返回属性表",
                      gp.get("ok") and isinstance(gp.get("properties"), dict),
                      f"{len(gp.get('properties', {}))} 项属性")

                props = gp.get("properties", {})
                supported = [n for n, p in props.items() if p.get("supported")]
                if supported:
                    name = supported[0]
                    cur = props[name].get("value")
                    sp = await call(session, "set_camera_property",
                                    {"cam_id": cam_id, "property": name, "value": cur})
                    check("set_camera_property 生效并回读",
                          sp.get("ok") and "actual_value" in sp,
                          f"{name}={sp.get('actual_value')}")
                else:
                    sp = await call(session, "set_camera_property",
                                    {"cam_id": cam_id, "property": "brightness", "value": 128})
                    check("set_camera_property 不崩（设备不支持也返回结构）",
                          sp.get("ok") and "actual_value" in sp,
                          f"set_ack={sp.get('set_ack')}")

            # ----------------------------------------------------------
            # 5. mock 远程摄像头
            # ----------------------------------------------------------
            print("[5/8] 远程摄像头（mock IP Camera）")
            mock_url, mock = start_mock(port=0)
            try:
                ar = await call(session, "add_remote_camera", {"url": mock_url})
                check("add_remote_camera 注册成功",
                      ar.get("ok") and ar["camera"]["kind"] == "remote",
                      f"id={ar['camera']['id']} backend={ar['camera']['backend']}")
                ip_id = ar["camera"]["id"]

                data2 = await call(session, "list_cameras", {})
                ids = [c["id"] for c in data2["cameras"]]
                check("list_cameras 含远程摄像头", ip_id in ids)

                cf = await call(session, "capture_frame",
                                {"cam_id": ip_id, "width": 640, "height": 480})
                check("远程摄像头拍帧成功",
                      cf.get("ok") and cf.get("jpeg_base64"),
                      f"{cf.get('width')}x{cf.get('height')}")

                gp2 = await call(session, "get_camera_property", {"cam_id": ip_id})
                check("远程属性探测不崩", gp2.get("ok") or "error" in gp2)

                rm = await call(session, "remove_remote_camera", {"cam_id": ip_id})
                check("remove_remote_camera 移除成功", rm.get("ok"))
            finally:
                mock.stop()

            # ----------------------------------------------------------
            # 6. 双摄并发
            # ----------------------------------------------------------
            print("[6/8] 双摄并发（本地 + mock 远程）")
            mock_url2, mock2 = start_mock(port=0)
            try:
                ar2 = await call(session, "add_remote_camera", {"url": mock_url2})
                ip2 = ar2["camera"]["id"]
                st = await call(session, "capture_stereo",
                                {"cam1_id": local_id, "cam2_id": ip2})
                check("capture_stereo 双路成功",
                      st.get("ok") and len(st.get("frames", [])) == 2,
                      f"drift_ms={st.get('drift_ms')} aligned={st.get('aligned')}")
                check("时间戳对齐信息存在",
                      "drift_ms" in st and "aligned" in st and "frames" in st)
            finally:
                mock2.stop()

            # ----------------------------------------------------------
            # 7. 智能拍照 / 对焦 / 曝光
            # ----------------------------------------------------------
            print("[7/9] 智能拍照 / 对焦 / 曝光")
            sc = await call(session, "smart_capture",
                            {"cam_id": local_id, "width": 320, "height": 240})
            check("smart_capture 成功",
                  sc.get("ok") and sc.get("scene") in (
                      "dark", "normal", "overexposed")
                  and sc.get("jpeg_base64"),
                  f"scene={sc.get('scene')} conf={sc.get('scene_confidence')}")
            af = await call(session, "auto_focus",
                            {"cam_id": local_id, "frames": 3})
            check("auto_focus 返回最清晰帧",
                  af.get("ok") and "sharpness" in af and af.get("jpeg_base64"),
                  f"sharpness={af.get('sharpness')}")
            se = await call(session, "set_exposure",
                            {"cam_id": local_id, "mode": "auto"})
            check("set_exposure 调用不崩",
                  se.get("ok") and "supported" in se,
                  f"supported={se.get('supported')}")

            # ----------------------------------------------------------
            # 8. 视觉识别（可选链路）
            # ----------------------------------------------------------
            print("[8/9] 视觉识别")
            if with_gestures:
                dg = await call(session, "detect_gestures",
                                {"cam_id": local_id, "num_hands": 1})
                check("手势识别链路", dg.get("ok") and "hands" in dg,
                      f"检测到 {dg.get('num_hands')} 只手")
            else:
                print("  （跳过手势识别，--gestures 可启用）")
            if with_objects:
                dobj = await call(session, "detect_objects", {"cam_id": local_id})
                check("物体检测链路", "detections" in dobj)
            else:
                print("  （跳过物体检测，--objects 可启用，需安装 ultralytics）")

            # ----------------------------------------------------------
            # 9. 画面理解（无 Ollama 时返回错误结构，不崩即可）
            # ----------------------------------------------------------
            print("[9/9] 画面理解")
            asc = await call(session, "analyze_scene", {"cam_id": local_id})
            if asc.get("ok"):
                check("analyze_scene 返回描述", "description" in asc,
                      f"{asc.get('description', '')[:40]}...")
            else:
                check("analyze_scene 无 Ollama 时优雅报错",
                      "error" in asc, asc.get("error", "")[:40])

            print(f"\n结果: {PASS} 通过, {FAIL} 失败")
            return FAIL


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--gestures", action="store_true", help="追加手势识别链路")
    parser.add_argument("--objects", action="store_true", help="追加 YOLO 检测链路")
    args = parser.parse_args()
    fail = asyncio.run(main(args.gestures, args.objects))
    sys.exit(1 if fail else 0)
