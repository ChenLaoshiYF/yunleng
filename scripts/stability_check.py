"""稳定性自检：每个关键功能重复跑 N 遍（默认 3），全部通过才返回 0。

覆盖：摄像头枚举 / 拍照 / 手势识别 / 属性读取 / 自动对焦 / 曝光控制

用法:
    python scripts/stability_check.py [--runs 3] [--camera 0]

规则：任一遍失败即整体失败（返回码 1）。
"""

from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from camera_mcp.camera import manager
from camera_mcp import gestures

FAILS = []
R = 0


def run(name: str, fn):
    """执行 fn() 并打印结果；失败记录到 FAILS。"""
    global R
    for i in range(R):
        t0 = time.time()
        try:
            r = fn()
            ok = bool(r.get("ok", True))
            detail = str(r.get("detail", r.get("error", "")))[:100]
        except Exception as e:
            ok, detail = False, f"{type(e).__name__}: {e}"
        dt = f"{time.time()-t0:.1f}s"
        mark = "✔" if ok else "✘"
        print(f"  [{mark}] {name} 第{i+1}/{R} 遍 {dt}  {detail}")
        if not ok:
            FAILS.append(f"{name} 第{i+1}遍: {detail}")


def main():
    global R
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3, help="每功能重复次数")
    parser.add_argument("--camera", type=int, default=0, help="本地摄像头 index")
    args = parser.parse_args()
    R = args.runs
    cam = str(args.camera)

    print(f"=== 稳定性自检：{R} 遍 × 6 项功能 ===\n")

    print("[1/6] 摄像头枚举")
    run("discover", lambda: manager.discover(refresh=True) and {"ok": True})

    print("[2/6] 拍照")
    def _capture():
        f, _, err = manager.capture(cam)
        return {"ok": f is not None, "detail": f"{f.shape[1]}x{f.shape[0]}" if f is not None else err}
    run("capture", _capture)

    print("[3/6] 手势识别")
    def _gestures():
        f, _, err = manager.capture(cam)
        if f is None:
            return {"ok": False, "detail": err}
        return {"ok": True, "detail": f"hands={len(gestures.get_detector().detect(f))}"}
    run("detect_gestures", _gestures)

    print("[4/6] 属性读取")
    run("get_properties", lambda: {
        "ok": True, "detail": f"{len(manager.get_properties(cam).get('properties', {}))} props"})

    print("[5/6] 自动对焦")
    run("auto_focus", lambda: (
        lambda r: {"ok": r["ok"], "detail": f"sharpness={r.get('sharpness')}"}
    )(manager.auto_focus(cam, frames=4)))

    print("[6/6] 曝光控制")
    run("set_exposure(auto)", lambda: manager.set_exposure(cam, mode="auto"))
    run("set_exposure(manual)", lambda: manager.set_exposure(cam, mode="manual", value=-6))

    print(f"\n=== 结果: {8 * R} 次执行, 失败 {len(FAILS)} ===\n")
    if FAILS:
        for f in FAILS:
            print("  ✘", f)
        sys.exit(1)
    print("全部通过 ✔")
    sys.exit(0)


if __name__ == "__main__":
    main()
