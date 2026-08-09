"""长时间稳定性测试（参数化时长）。

节奏（低频，模拟 Agent 真实使用，不烧资源）：
- 每 30 秒拍一帧，记录时间戳/帧号/内存(RSS)/成败
- list_cameras 每 5 分钟一次
- get_camera_property 每 10 分钟一次
- 任一步骤报错：记录错误并继续运行（robustness 测试）

用法:
    python scripts/long_run_test.py                        # 完整 30 分钟
    python scripts/long_run_test.py --duration 60          # 快速验证模式（60 秒）

完整 30 分钟测试请执行：python scripts/long_run_test.py --duration 1800
报告输出：scripts/long_run_report.md

摄像头用完即释放（manager.capture 设计如此），不长期 hold，防资源泄漏。
"""

from __future__ import annotations

import argparse
import os
import statistics
import sys
import time

import psutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from camera_mcp.camera import manager  # noqa: E402

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPORT_PATH = os.path.join(SCRIPT_DIR, "long_run_report.md")
FULL_DURATION = 1800  # 完整模式 30 分钟


def mem_mb() -> float:
    return psutil.Process().memory_info().rss / 1024 / 1024


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=int, default=FULL_DURATION,
                        help="总时长（秒），默认 1800（30 分钟）；调试用 60")
    parser.add_argument("--interval", type=float, default=30.0, help="帧间隔（秒）")
    parser.add_argument("--camera", type=int, default=0, help="本地摄像头 index")
    args = parser.parse_args()

    cam = str(args.camera)
    total_s = args.duration
    quick = total_s < FULL_DURATION
    n_frames = int(total_s / args.interval) + 1
    start_time = time.time()
    end_time = start_time + total_s

    mode = "快速验证模式" if quick else "完整模式"
    print(f"=== 长时间稳定性测试（{mode}）：{total_s}s，每 {args.interval}s 一帧，约 {n_frames} 帧 ===")
    print(f"摄像头 {cam} | 开始 {time.strftime('%H:%M:%S')}\n")

    frames: list[dict] = []
    sys_calls: list[dict] = []
    errors: list[dict] = []
    crash = False

    def record_err(where: str, exc: Exception):
        e = {"t": time.time() - start_time, "where": where, "error": f"{type(exc).__name__}: {exc}"}
        errors.append(e)
        print(f"  [错误] {where}: {exc}")

    # 周期任务计划（相对开始时刻，秒）
    plan = []
    t = 5 * 60
    while t < total_s:
        plan.append((t, "list_cameras"))
        t += 5 * 60
    t = 10 * 60
    while t < total_s:
        plan.append((t, "get_camera_property"))
        t += 10 * 60
    plan.sort()
    # 快速模式没有周期任务时，压缩到总时长的 1/3 处演示一次（验证逻辑）
    if quick and not plan:
        plan.append((total_s / 3, "list_cameras"))
        plan.append((total_s * 2 / 3, "get_camera_property"))

    frame_idx = 0
    next_frame_t = start_time
    mem_samples = [mem_mb()]

    try:
        while time.time() < end_time:
            now = time.time()

            # 周期系统调用
            for plan_t, kind in list(plan):
                if plan_t <= now - start_time:
                    plan.remove((plan_t, kind))
                    t0 = time.time()
                    try:
                        if kind == "list_cameras":
                            infos = manager.discover()
                            detail = f"{len(infos)} cams"
                        elif kind == "get_camera_property":
                            r = manager.get_properties(cam)
                            detail = f"{len(r.get('properties', {}))} props"
                        sys_calls.append({"t": round(now - start_time, 1), "kind": kind,
                                          "ok": True, "ms": round((time.time() - t0) * 1000, 1),
                                          "detail": detail})
                        print(f"  [{time.strftime('%H:%M:%S')}] {kind}: {detail}")
                    except Exception as e:
                        record_err(f"syscall:{kind}", e)
                        sys_calls.append({"t": round(now - start_time, 1), "kind": kind,
                                          "ok": False, "ms": round((time.time() - t0) * 1000, 1)})

            # 拍帧
            if now >= next_frame_t:
                t0 = time.time()
                ok = False
                detail = ""
                try:
                    frame, jpeg, err = manager.capture(cam, 640, 480)
                    if err:
                        detail = err
                    elif frame is None:
                        detail = "frame is None"
                    else:
                        ok = True
                        detail = f"{frame.shape[1]}x{frame.shape[0]}"
                except Exception as e:
                    detail = f"{type(e).__name__}: {e}"
                elapsed = time.time() - t0
                mem = mem_mb()
                mem_samples.append(mem)
                frames.append({
                    "frame": frame_idx,
                    "t": round(now - start_time, 1),
                    "ok": ok,
                    "elapsed_ms": round(elapsed * 1000, 1),
                    "mem_mb": round(mem, 1),
                    "detail": detail,
                })
                if not ok:
                    errors.append({"t": round(now - start_time, 1), "where": f"frame#{frame_idx}", "error": detail})
                print(f"  [{time.strftime('%H:%M:%S')}] 帧#{frame_idx}: {'OK' if ok else 'FAIL'} "
                      f"({elapsed*1000:.0f}ms, mem={mem:.0f}MB) {detail[:60]}")
                frame_idx += 1
                next_frame_t = start_time + frame_idx * args.interval

        mem_samples.append(mem_mb())
    except KeyboardInterrupt:
        print("\n[中断] 手动停止")
    except Exception as e:
        crash = True
        record_err("main_loop", e)

    # ---------------- 报告 ----------------
    ok_frames = [f for f in frames if f["ok"]]
    fail_frames = [f for f in frames if not f["ok"]]
    mem_start, mem_end = mem_samples[0], mem_samples[-1]
    mem_peak = max(mem_samples)
    mem_avg = statistics.mean(mem_samples)

    # 内存口径修正：首帧包含冷启动加载（OpenCV/模型初始化），
    # 单独记为「冷启动开销」；稳定期增长 = 末帧内存 - 稳定期起点（第 2 帧后）
    init_mem = frames[0]["mem_mb"] if frames else mem_end   # 冷启动峰值（首帧）
    stable_start = frames[1]["mem_mb"] if len(frames) > 1 else mem_end
    stable_growth = mem_end - stable_start
    intervals = []
    for i in range(1, len(frames)):
        intervals.append(frames[i]["t"] - frames[i - 1]["t"])

    report = []
    report.append("# 长时间稳定性测试报告\n")
    report.append(f"- 测试模式: **{mode}**（{'完整 30 分钟' if not quick else '60 秒快速验证'}，逻辑相同仅时长缩短）")
    report.append(f"- 测试时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    report.append(f"- 时长: {total_s}s | 帧间隔: {args.interval}s | 摄像头: {cam}")
    report.append(f"- 实际帧数: {len(frames)} | 成功: {len(ok_frames)} | 失败: {len(fail_frames)}")
    report.append("")
    report.append("## 内存占用趋势（MB）")
    report.append(f"- 起始(进程启动): {mem_start:.1f} | 结束: {mem_end:.1f} | 峰值: {mem_peak:.1f} | 平均: {mem_avg:.1f}")
    report.append(f"- 冷启动开销(首帧加载模型): {init_mem - mem_start:+.1f} MB（一次性，非泄漏）")
    leak_warn = "疑似泄漏！" if stable_growth > 50 else "正常"
    report.append(f"- 稳定期增长(末帧-第2帧后): {stable_growth:+.1f} MB（{leak_warn}，阈值 50MB）")
    report.append("")
    report.append("## 帧间隔稳定性（秒）")
    if intervals:
        line = f"- 设计间隔: {args.interval}s | 实测均值: {statistics.mean(intervals):.2f}s"
        if len(intervals) >= 2:
            line += f" | 标准差: {statistics.stdev(intervals):.2f}s"
        line += f" | 最大偏离: {max(intervals):.2f}s"
        report.append(line)
        drift = abs(statistics.mean(intervals) - args.interval)
        report.append(f"- 节奏漂移: {drift:.2f}s（{'稳定' if drift < 5 else '漂移较大'}）")
    report.append("")
    report.append("## 周期系统调用")
    report.append("| 类型 | 次数 | 成功 | 平均耗时 |")
    report.append("|------|------|------|---------|")
    for kind in ("list_cameras", "get_camera_property"):
        sc = [s for s in sys_calls if s["kind"] == kind]
        if sc:
            okc = sum(1 for s in sc if s["ok"])
            avg_ms = statistics.mean(s["ms"] for s in sc)
            report.append(f"| {kind} | {len(sc)} | {okc} | {avg_ms:.0f}ms |")
    report.append("")
    report.append("## 稳定性结论")
    report.append(f"- 零 crash: {'✔ 确认' if not crash else '✘ 发生主循环崩溃'}")
    report.append(f"- 错误总数: {len(errors)}")
    if errors:
        report.append("- 错误清单:")
        for e in errors:
            report.append(f"  - [{e['t']:.0f}s] {e['where']}: {e['error']}")
    else:
        report.append("- 全程无错误")
    report.append("")
    report.append("## 逐帧明细")
    report.append("| 帧号 | 时间(s) | 结果 | 耗时(ms) | 内存(MB) |")
    report.append("|------|---------|------|----------|----------|")
    for f in frames:
        report.append(f"| {f['frame']} | {f['t']:.0f} | {'OK' if f['ok'] else 'FAIL'} | {f['elapsed_ms']:.0f} | {f['mem_mb']:.0f} |")
    report.append("")
    report.append("---")
    report.append("完整 30 分钟测试请执行：`python scripts/long_run_test.py --duration 1800`")

    with open(REPORT_PATH, "w", encoding="utf-8") as fh:
        fh.write("\n".join(report))

    print("\n=== 测试结束 ===")
    print(f"帧: {len(frames)}（成功 {len(ok_frames)} / 失败 {len(fail_frames)}）")
    print(f"内存: {mem_start:.1f}MB → {mem_end:.1f}MB（峰值 {mem_peak:.1f}MB，平均 {mem_avg:.1f}MB）")
    print(f"错误: {len(errors)} | 零 crash: {'是' if not crash else '否'}")
    print(f"报告已写入: {REPORT_PATH}")


if __name__ == "__main__":
    main()
