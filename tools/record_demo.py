#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OctoSense 日历 · 视频录制器
================================
跑 card-host（剥掉签名、本地直跑），按 16 段剧情驱动 UI，每段抓 1 帧真截图，
合成两个成品：
  * 3 分钟完整版（答辩 / 完整流程演示用）
  * 1 分 30 秒精简版（GitHub README / App Hub 商店用）

每帧都是 `curl 127.0.0.1:PORT/g?raw=1` 抓的真截图，不是渲染占位；
MP4 用 imageio + 内置 ffmpeg 拼装（managed venv，无 brew 依赖）。

跑法：
    python3 tools/record_demo.py
    # 或者 python3 tools/record_demo.py --fps 24 --port 8932

会产物落：
    .runtime/demo-frames/  每段一张 PNG（保留作证据）
    .runtime/octosense-demo-3min.mp4
    .runtime/octosense-demo-1min30.mp4
"""

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

# ── 常量 ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
BINARY = ROOT / "_toolchain" / "OctoSense-App-Hub" / "target" / "release" / "card-host"
BUNDLE_ORIG = ROOT / "bundle"
BUNDLE_DEV = ROOT / ".runtime" / "bundle-recording"  # 剥签名的临时 bundle
FRAME_DIR = ROOT / ".runtime" / "demo-frames"
HOST_LOG = ROOT / ".runtime" / "demo-host.log"
APP_DATA = ROOT / ".runtime" / "demo-app-data"

# 设计语言色（与 ui-design-v1.html 一致）
INK = (25, 23, 20)         # #191714
PAPER = (250, 249, 247)    # #faf9f7
ACCENT = (180, 83, 31)     # #b4531f
INK2 = (107, 101, 96)      # #6b6560


# ── 工具 ────────────────────────────────────────────────────────────────
def log(msg, end="\n"):
    print(f"[record] {msg}", file=sys.stderr, end=end)
    sys.stderr.flush()


def run(cmd, **kw):
    return subprocess.run(cmd, cwd=str(ROOT), **kw)


def wait_port(port, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2) as r:
                r.read()
                return True
        except Exception:
            time.sleep(0.5)
    return False


def grab(port, out_path: Path, settle=1.0):
    """从宿主抓一帧 PNG。"""
    deadline = time.time() + 5
    last_data = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/g?raw=1&t={int(time.time()*1000)}",
                timeout=5,
            ) as r:
                data = r.read()
            if last_data is not None and last_data == data and len(data) > 10000:
                out_path.write_bytes(data)
                return out_path
            last_data = data
        except Exception as e:
            log(f"  grab retry: {e}")
        time.sleep(settle)
    # 最后还是写下来
    if last_data:
        out_path.write_bytes(last_data)
    return out_path


# ── Bundle 剥签名 ────────────────────────────────────────────────────────
def make_dev_bundle():
    """拷一份 bundle、把 manifest.json 的 signature 删掉，避免 RefuseAllSignatures。"""
    if BUNDLE_DEV.exists():
        shutil.rmtree(BUNDLE_DEV)
    shutil.copytree(BUNDLE_ORIG, BUNDLE_DEV, symlinks=False)
    mf = BUNDLE_DEV / "manifest.json"
    obj = json.loads(mf.read_text(encoding="utf-8"))
    if "signature" in obj.get("integrity", {}):
        del obj["integrity"]["signature"]
        mf.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"已剥签名 → {mf}")
    else:
        log(f"manifest 本来就无签名: {mf}")


def cleanup_dev_bundle():
    if BUNDLE_DEV.exists():
        shutil.rmtree(BUNDLE_DEV)
        log(f"已清理临时 bundle: {BUNDLE_DEV}")


# ── 宿主 ────────────────────────────────────────────────────────────────
def kill_host():
    subprocess.run(["pkill", "-9", "-f", "card-host"], check=False)
    time.sleep(0.5)


def boot_host(port):
    kill_host()
    APP_DATA.mkdir(parents=True, exist_ok=True)
    HOST_LOG.parent.mkdir(parents=True, exist_ok=True)
    if HOST_LOG.exists():
        HOST_LOG.unlink()
    env = os.environ.copy()
    env["MAKEPAD_REMOTE"] = str(port)
    env["NO_PROXY"] = "127.0.0.1,localhost"
    env["no_proxy"] = env["NO_PROXY"]
    p = subprocess.Popen(
        [str(BINARY), "--bundle", str(BUNDLE_DEV),
         "--app-data", str(APP_DATA),
         "--allow-unsigned", "--stamp"],
        cwd=str(ROOT),
        stdout=HOST_LOG.open("wb"),
        stderr=subprocess.STDOUT,
        env=env,
    )
    log(f"spawned card-host pid={p.pid}")
    if not wait_port(port, timeout=30):
        log(f"FATAL: 宿主未就绪，最后 20 行日志：")
        subprocess.run(["tail", "-20", str(HOST_LOG)])
        sys.exit(1)
    log(f"宿主就绪 port={port}")
    # 让第一帧画完
    time.sleep(2.5)
    return p


# ── e2e 驱动 ────────────────────────────────────────────────────────────
def e2e(cmd, *args, timeout=60):
    r = subprocess.run(
        ["python3", "tools/e2e.py", cmd, *args],
        cwd=str(ROOT), capture_output=True, text=True, timeout=timeout,
    )
    if r.returncode != 0:
        log(f"  WARN e2e {cmd} rc={r.returncode}")
        if r.stderr.strip():
            log(f"    stderr: {r.stderr.strip()[:200]}")
    return r


# ── 字幕 / 标题卡片 ────────────────────────────────────────────────────
# 标准尺寸（必须与字幕合成图一致，否则 mp4 拼装报 ValueError）
CAPTION_BAR_H = 140
FRAME_W, FRAME_H = 824, 1702        # card-host 输出
OUT_W, OUT_H = 824, 1702 + CAPTION_BAR_H  # 加字幕条后 824x1842


def make_caption_card(text_lines, size=None, bg=PAPER):
    """标题 / 结尾卡：尺寸与字幕合成图一致，避免 mp4 帧大小不一致。"""
    from PIL import Image, ImageDraw, ImageFont
    if size is None:
        size = (OUT_W, OUT_H)
    w, h = size
    img = Image.new("RGB", size, bg)
    draw = ImageDraw.Draw(img)
    # 顶部装饰条（赤陶）
    draw.rectangle([0, 0, w, 12], fill=ACCENT)
    # 底部装饰条（黑底 + 赤陶窄线，对齐字幕条位置）
    draw.rectangle([0, h - CAPTION_BAR_H, w, h], fill=INK)
    draw.rectangle([0, h - CAPTION_BAR_H, w, h - CAPTION_BAR_H + 4], fill=ACCENT)
    # 文字（中文 → 必须用系统中文字体）
    candidates = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/Library/Fonts/Songti.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
    ]
    font_path = next((p for p in candidates if Path(p).exists()), None)
    # 自动缩字：每行单独按可用宽度找最大字号（左右各留 48px 边距）
    if font_path is None:
        log("WARN: 找不到系统中文字体，使用默认")
        fonts = [(ImageFont.load_default(), 0, 0) for _ in text_lines]
    else:
        fonts = [_fit_text(draw, line, font_path, max_width=w - 96,
                           start_size=80, min_size=36)
                 for line in text_lines]
    # 居中竖排（取上半区，避免压到底部字幕条）
    y = h // 6
    for (font, tw, th), line in zip(fonts, text_lines):
        draw.text(((w - tw) // 2, y), line, fill=INK, font=font)
        y += max(th + 18, 80)
    return img


def _fit_text(draw, text, font_path, max_width, start_size=44, min_size=22):
    """找一个字号让 text 在 max_width 内能放下。返回 (font, w, h)。"""
    from PIL import ImageFont
    sz = start_size
    while sz >= min_size:
        f = ImageFont.truetype(font_path, sz)
        bbox = draw.textbbox((0, 0), text, font=f)
        if bbox[2] - bbox[0] <= max_width:
            return f, bbox[2] - bbox[0], bbox[3] - bbox[1]
        sz -= 2
    f = ImageFont.truetype(font_path, min_size)
    bbox = draw.textbbox((0, 0), text, font=f)
    return f, bbox[2] - bbox[0], bbox[3] - bbox[1]


def composite_caption(screenshot: Path, caption_text: str, out: Path,
                     bar_height=CAPTION_BAR_H):
    """把 screenshot 下方贴一条字幕条，输出尺寸固定为 (OUT_W, OUT_H)。"""
    from PIL import Image, ImageDraw, ImageFont
    img = Image.open(screenshot).convert("RGB")
    if img.size != (FRAME_W, FRAME_H):
        img = img.resize((FRAME_W, FRAME_H), Image.LANCZOS)
    canvas = Image.new("RGB", (OUT_W, OUT_H), PAPER)
    canvas.paste(img, (0, 0))
    draw = ImageDraw.Draw(canvas)
    # 字幕条
    draw.rectangle([0, FRAME_H, OUT_W, OUT_H], fill=INK)
    draw.rectangle([0, FRAME_H, OUT_W, FRAME_H + 4], fill=ACCENT)
    # 字（自动缩字让 caption 放进字幕条，左右留 32px 边距）
    candidates = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
    ]
    font_path = next((p for p in candidates if Path(p).exists()), None)
    if font_path is None:
        font = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), caption_text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    else:
        font, tw, th = _fit_text(draw, caption_text, font_path,
                                 max_width=OUT_W - 32)
    # 居中
    draw.text(((OUT_W - tw) // 2, FRAME_H + (bar_height - th) // 2 - 8),
              caption_text, fill=PAPER, font=font)
    canvas.save(out)
    return out


# ── 音频层（背景 pad + TTS 关键节点旁白）───────────────────────────────
def _find_ffmpeg() -> Path:
    """定位 ffmpeg 二进制。

    优先用 imageio_ffmpeg 随包带的那个（无 brew 依赖、跨机器一致）；
    拿不到再退回 PATH 里的 ffmpeg。
    """
    try:
        import imageio_ffmpeg

        return Path(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:
        found = shutil.which("ffmpeg")
        if not found:
            raise SystemExit(
                "找不到 ffmpeg：请先 `pip install imageio-ffmpeg`，"
                "或把 ffmpeg 放进 PATH。"
            )
        return Path(found)


FFMPEG_BIN = _find_ffmpeg()

# TTS 节点：视频时间戳（秒）→ 中文短句（用 macOS `say -v Tingting` 合成）
# 选节点原则：硬证据或情感转折点；句子要短（≤ 8 字）让 TTS 节奏紧凑
TTS_ANCHORS = {
    "00_title.png":        "OctoSense 日历，意图即应用。",
    "16_conflict_detail.png": "重叠三十分钟。",
    "17_advice_applied.png":  "一键消解，剩余零处冲突。",
    "19_roundtrip.png":       "新增零，改期零，跳过四。",
}

# BGM 全局音量
# 历史：0.55（合成 pad，太大）→ 0.22（用户"调小"，太小）→ 0.35（用户"大一点点"，铺底/对白比 1.0:0.35 ≈ -9 dB）
BG_VOL = 0.35

# 用户提供的源 BGM 路径（如 bensound-sunny.mp3）。
# 如果文件存在，make_bgm 会自动用它代替 aevalsrc 合成。
# 预期来源：Bensound「Sunny」（CC BY，需注明 Music by www.bensound.com）
BENSOURCE_PATH = Path(__file__).parent.parent / ".runtime" / ".audio" / "sunny-source.mp3"


def make_bgm(seconds: float, out_path: Path, seed: int = 42):
    """生成铺底 BGM。
    优先用源 mp3（BENSOURCE_PATH，存在就用它循环 + 降音量 + 铺到目标时长），
    否则回退到 aevalsrc 合成 pad。
    """
    if BENSOURCE_PATH.exists() and BENSOURCE_PATH.stat().st_size > 1024:
        _make_bgm_from_source(seconds, out_path)
    else:
        _make_bgm_synth(seconds, out_path, seed)


def _make_bgm_from_source(seconds: float, out_path: Path):
    """从用户提供的 mp3 切到目标时长 + 降音量。
    用 ffmpeg 的 -stream_loop -1 把短曲子循环铺满，再叠 volume=BG_VOL。
    """
    cmd = [
        str(FFMPEG_BIN), "-y", "-hide_banner", "-loglevel", "error",
        "-stream_loop", "-1", "-i", str(BENSOURCE_PATH),
        "-t", str(seconds),                    # 切到目标时长
        "-af", f"volume={BG_VOL}",             # 一次性降音量
        "-ac", "2", "-ar", "44100",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)
    log(f"  BGM: {out_path.name} ({seconds:.1f}s) ← 源 {BENSOURCE_PATH.name} "
        f"loop+vol={BG_VOL}")


def _make_bgm_synth(seconds: float, out_path: Path, seed: int = 42):
    """合成柔和 pad 背景音（aevalsrc，联网失败时的 fallback）。
    听感明显比真实 mp3 单薄，仅用于网络不可用场景。
    """
    expr = (
        f"0.16*sin(2*PI*220*t)*(0.5+0.5*sin(2*PI*0.27*t)) + "
        f"0.08*sin(2*PI*330*t)*(0.5+0.5*sin(2*PI*0.19*t)) + "
        f"0.04*sin(2*PI*165*t)*(0.5+0.5*sin(2*PI*0.13*t)) + "
        f"0.025*(random({seed})*2-1)"
    )
    cmd = [
        str(FFMPEG_BIN), "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi",
        "-i", f"aevalsrc={expr}:d={seconds}:s=44100",
        "-af", "lowpass=f=1500,volume=0.55",
        "-ac", "2", "-ar", "44100",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)
    log(f"  BGM: {out_path.name} ({seconds:.1f}s) ← aevalsrc 合成（fallback）")


def make_tts(text: str, voice: str, out_path: Path, rate: int = 180):
    """macOS `say` 合成中文 TTS → AIFF。rate 是每分钟字数（180 ≈ 略快）。"""
    subprocess.run(["say", "-v", voice, "-r", str(rate),
                    "-o", str(out_path), text], check=True)


def get_audio_duration(path: Path) -> float:
    """读 AIFF/WAV 时长（秒）。
    ⚠️ 不能用 Python wave 模块：macOS `say` 输出的是 AIFF-C（big-endian PCM），
    wave 只认 RIFF/WAV。统一走 ffprobe。
    """
    r = subprocess.run(
        [str(FFMPEG_BIN), "-i", str(path)],
        capture_output=True, text=True,
    )
    for line in r.stderr.splitlines():
        if line.startswith("  Duration:"):
            # "  Duration: 00:00:02.86, start: 0.000000, bitrate: ..."
            t = line.split(",")[0].split(":", 1)[1].strip()
            h, m, s = t.split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)
    raise RuntimeError(f"找不到 duration in ffprobe 输出 for {path}")


def mux_audio(video_path: Path, bgm_path: Path, tts_segments: list[tuple],
              out_path: Path):
    """把 BGM 和 TTS 按时戳混好，再 mux 进视频。
    tts_segments: [(start_seconds, tts_path), ...]
    ⚠️ 视频是 input 0，bgm 是 input 1，TTS 是 input 2/3/4/...
    音量策略：BGM=BG_VOL（0.22，铺底不抢戏）；TTS=1.0（始终清晰）
    """
    inputs = ["-i", str(video_path), "-i", str(bgm_path)]
    fc_parts = [f"[1:a]volume={BG_VOL}[bgm]"]   # BGM 降音量（用户要求"调小"）
    next_input_id = 2  # 下一个 input 是 TTS
    tts_mix_labels = []
    for i, (start_sec, tts_path) in enumerate(tts_segments):
        inputs.extend(["-i", str(tts_path)])
        delay_ms = int(start_sec * 1000)
        lbl_in = f"[{next_input_id}:a]"
        lbl_out = f"[tts{i}]"
        fc_parts.append(
            f"{lbl_in}adelay={delay_ms}|{delay_ms},apad,volume=1.0{lbl_out}"
        )
        tts_mix_labels.append(lbl_out)
        next_input_id += 1
    # 所有 TTS 混成一条
    tts_sum = "".join(tts_mix_labels) + f"amix=inputs={len(tts_mix_labels)}:normalize=0[tts]"
    fc_parts.append(tts_sum)
    # BGM + TTS 混合（BGM=BG_VOL=0.22，TTS=1.0，TTS 永远压住 BGM）
    fc_parts.append(
        f"[bgm][tts]amix=inputs=2:weights={BG_VOL} 1.0:duration=first:normalize=0[a]"
    )
    cmd = [
        str(FFMPEG_BIN), "-y", "-hide_banner", "-loglevel", "error",
        *inputs,
        "-filter_complex", ";".join(fc_parts),
        "-map", "0:v",          # 视频流（用 :v 而非 :v:0，更稳）
        "-map", "[a]",          # 混好的音频
        "-c:v", "copy",         # 视频直接拷贝，不重编码
        "-c:a", "aac", "-b:a", "128k",
        "-shortest",
        "-movflags", "+faststart",  # 把 moov 原子挪到文件头，浏览器能直接播
        str(out_path),
    ]
    subprocess.run(cmd, check=True)
    log(f"  muxed → {out_path.name} ({out_path.stat().st_size/1024/1024:.2f} MiB)")


def add_audio_to_video(video_path: Path, out_path: Path,
                       anchors: dict, storyboard_fn, fps: int = 24):
    """给视频加 BGM + TTS。
    anchors: {frame_name: tts_text} —— 用 storyboard 累计时间算偏移。
    storyboard_fn: callable 返回 story 列表（用来算每段时长）。
    """
    story = storyboard_fn()
    cum = 0.0
    tts_segs = []
    audio_dir = video_path.parent / ".audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    for name, captions, action, hold, *rest in story:
        if name in anchors:
            voice = "Tingting"
            tts_text = anchors[name]
            tts_path = audio_dir / f"tts-{name.replace('.png', '')}.aiff"
            try:
                make_tts(tts_text, voice, tts_path)
            except Exception as e:
                log(f"  WARN tts {name}: {e}")
                cum += hold
                continue
            tts_segs.append((cum, tts_path))
        cum += hold
    if not tts_segs:
        log("  no TTS anchors,跳过音频")
        return
    log(f"  TTS 段数: {len(tts_segs)}, 总视频时长: {cum:.1f}s")
    bgm_path = audio_dir / "bgm.wav"
    make_bgm(cum, bgm_path)
    mux_audio(video_path, bgm_path, tts_segs, out_path)


# ── 拼 mp4 ─────────────────────────────────────────────────────────────
def compose_mp4(frames_with_durations, out_path: Path, fps=24):
    """frames_with_durations: [(PIL.Image, hold_seconds), ...]"""
    import imageio.v2 as imageio
    tmp = out_path.with_suffix(".tmp.mp4")
    writer = imageio.get_writer(
        str(tmp), fps=fps, codec="libx264", quality=8,
        pixelformat="yuv420p", macro_block_size=1,
    )
    total = 0.0
    for img, dur in frames_with_durations:
        n = max(1, int(round(dur * fps)))
        arr = __import__("numpy").asarray(img)
        for _ in range(n):
            writer.append_data(arr)
        total += dur
        log(f"  + {n}帧 ×{dur:.1f}s  (累计 {total:.1f}s)")
    writer.close()
    # 改后缀
    tmp.replace(out_path)
    log(f"  → {out_path}  ({out_path.stat().st_size/1024/1024:.2f} MiB)")
    return out_path


# ── 剧情 ──────────────────────────────────────────────────────────────
# 每一段 = (frame_filename, [caption_lines], action, hold_seconds)
def storyboard():
    """3 分钟完整版（约 21 段 / ~190 秒）。每段 hold 时长按"评委能读完字幕+看一眼画面"调。
    增项：节假日视图、节日来源切换、4 个分区 tab 巡览（待办/心情/目标/时光）、月历翻月。
    """
    return [
        # ── 0. 标题卡 ──
        ("00_title.png", ["OctoSense 日历", "会议改期冲突 · 场景演示", "GOSIM Agentic App 2026 · OMA"],
         None, 8.0),
        # ── 1. 空状态 ──
        ("01_empty.png", ["空状态 · 事件库 0 个", "核心日历在本机 · 天气只读一项不上传"],
         None, 7.0),
        # ── 2. 月历翻到 9 月（看国庆放假安排）──
        ("02_sept.png", ["翻到 2026 年 9 月", "国庆节放假 · 调休补班标记"],
         lambda: e2e("goto", "2026-09"), 9.0),
        # ── 3. 节日来源切换：国际 ──
        ("03_fest_intl.png", ["节日来源 · 国际", "万圣节 / 感恩节 / 圣诞节"],
         lambda: e2e("cycle"), 9.0),
        # ── 4. 节日来源切换：全部 ──
        ("04_fest_all.png", ["节日来源 · 全部", "国内 + 国际节假日同时显示"],
         lambda: e2e("cycle"), 9.0),
        # ── 5. 翻回 2026-10 ──
        ("05_oct.png", ["翻回 2026 年 10 月", "现在看到的就是今天"],
         lambda: e2e("goto", "2026-10"), 7.0),
        # ── 6. 点「导入」展开面板 ──
        ("06_import_open.png", ["点「导入」", "面板展开 · 输入框可粘贴 ICS"],
         lambda: e2e("open"), 9.0),
        # ── 7. 灌入 seed.ics ──
        ("07_seed_filled.png", ["灌入 seed.ics", "3 个事件 · 1 全天 · 1 带时区"],
         lambda: e2e("fill", "seed.ics"), 9.0),
        # ── 8. 解析 + 写入 ──
        ("08_seed_written.png", ["点「解析」→「写入」", "已加载 3 个事件 · 零冲突"],
         lambda: (e2e("parse"), e2e("write")), 10.0),
        # ── 9. 切到「待办」分区 ──
        ("09_todo.png", ["切到「待办」分区", "复盘清单 · 改期 · 归档 · 四级优先级"],
         lambda: (e2e("cancel"), e2e("btn", "待办")), 9.0),
        # ── 10. 切到「心情」分区 ──
        ("10_mood.png", ["切到「心情」分区", "5 档心情 + 备注 · 月历汇总"],
         lambda: e2e("btn", "心情"), 9.0),
        # ── 11. 切到「目标」分区 ──
        ("11_goal.png", ["切到「目标」分区", "中长期目标 · 子任务 · 进度条"],
         lambda: e2e("btn", "目标"), 9.0),
        # ── 12. 切到「时光」分区（时间胶囊 / 小知识 / 节气）──
        ("12_time.png", ["切到「时光」分区", "时间胶囊 · 节气 · 历史上的今天"],
         lambda: e2e("btn", "时光"), 9.0),
        # ── 13. 切回「日程」主视图 ──
        ("13_back_cal.png", ["切回「日程」分区", "日历主视图 · 3 个事件已标到月历"],
         lambda: e2e("btn", "日程"), 7.0),
        # ── 14. 再点「导入」+ 灌入 conflict.ics ──
        ("14_conflict_filled.png", ["再点「导入」", "灌入 conflict.ics · 复赛宣讲会撞期"],
         lambda: (e2e("open"), e2e("fill", "conflict.ics")), 9.0),
        # ── 15. 写入 → 冲突检出 ──
        ("15_conflict_written.png", ["点「解析」→「写入」", "已写入 4 个事件 · 发现 1 处时间冲突"],
         lambda: (e2e("parse"), e2e("write")), 11.0),
        # ── 16. 展开冲突详情（关键硬证据 #1）──
        ("16_conflict_detail.png", ["点「详情」", "重叠 30 分钟 · 复赛宣讲会 vs 黑客松初赛截止", "权重更高者保留 · 一键消解"],
         lambda: e2e("more"), 13.0),
        # ── 17. 应用改期建议（关键硬证据 #2）──
        ("17_advice_applied.png", ["点「应用建议」", "已应用 1 条改期 · 剩余 0 处冲突"],
         lambda: e2e("advice"), 13.0),
        # ── 18. 导出 ICS（entry 框被 ICS 填满）──
        ("18_export.png", ["点「导出」", "输入框得到完整 ICS 文本 · RFC 5545"],
         lambda: (e2e("open"), e2e("export")), 11.0),
        # ── 18b. 导出文本存盘（hidden）──
        (None, ["导出文本落盘"], lambda: e2e("entry", str(FRAME_DIR / "exported.ics")), 0.0),
        # ── 19. 往返：导出文本原样回灌（关键硬证据 #3）──
        ("19_roundtrip.png", ["把导出 ICS 原样回灌", "新增 0 · 改期 0 · 跳过 4", "导出无损 · 字段全部保留"],
         lambda: (e2e("fill", str(FRAME_DIR / "exported.ics")),
                  e2e("parse"), e2e("write")), 13.0),
        # ── 20. 关于页 ──
        ("20_about.png", ["点「关于」", "Apache-2.0 · CC BY 4.0 (Noto)"],
         lambda: (e2e("cancel"), e2e("about")), 9.0),
        # ── 21. 结尾卡 ──
        ("99_outro.png", ["OctoSense 日历", "意图，即应用", "队伍 OMA · ody-cai / mark-liuzh"],
         None, 8.0),
    ]


def readme_storyboard():
    """README 短版（约 95 秒 / 13 帧）。复用主剧情抓到的帧。"""
    return [
        ("00_title.png", ["OctoSense 日历 · 90 秒演示"],
         None, 5.0),
        ("01_empty.png", ["空状态 · 0 个事件"],
         None, 5.0),
        ("02_sept.png", ["2026 年 9 月 · 国庆节放假"],
         None, 6.0),
        ("06_import_open.png", ["点「导入」· 面板展开"],
         None, 6.0),
        ("08_seed_written.png", ["灌入 seed · 写入 3 个事件"],
         None, 8.0),
        ("09_todo.png", ["切到「待办」分区"],
         None, 7.0),
        ("10_mood.png", ["切到「心情」分区"],
         None, 7.0),
        ("11_goal.png", ["切到「目标」分区"],
         None, 7.0),
        ("13_back_cal.png", ["切回主视图 · 事件已标"],
         None, 6.0),
        ("15_conflict_written.png", ["再灌入 · 发现 1 处时间冲突"],
         None, 7.0),
        ("16_conflict_detail.png", ["重叠 30 分钟 · 复赛宣讲会 vs 黑客松初赛截止"],
         None, 8.0),
        ("17_advice_applied.png", ["一键消解 · 剩余 0 处冲突"],
         None, 8.0),
        ("19_roundtrip.png", ["导出后回灌 · 新增 0 / 改期 0 / 跳过 4", "导出无损 · 字段全部保留"],
         None, 8.0),
        ("20_about.png", ["Apache-2.0 · CC BY 4.0 (Noto)"],
         None, 6.0),
        ("99_outro.png", ["意图即应用 · OMA"],
         None, 5.0),
    ]


# ── 主流程 ─────────────────────────────────────────────────────────────
def mux_only(args):
    """只跑音频层（BGM + TTS → mux 进视频），复用已有 frames 和已有 mp4。
    用法：python3 tools/record_demo.py --mux-only
    假设 .runtime/octosense-demo-3min.mp4 和 octosense-demo-1min30.mp4 已生成。
    """
    out_dir = Path(args.out_dir)
    log(f"=== mux-only（不驱动 host，不重抓帧）===")
    log(f"   BG_VOL={BG_VOL}, 源 mp3={BENSOURCE_PATH}")
    if not BENSOURCE_PATH.exists():
        log(f"❌ 源 mp3 不存在: {BENSOURCE_PATH}，无法用源版本")
        return

    # 复用 main 里一样的流程：3min 版 + 1min30 版
    FRAME_DIR.mkdir(parents=True, exist_ok=True)

    log("\n3 分钟版：")
    v3 = out_dir / "octosense-demo-3min.mp4"
    a3 = out_dir / "octosense-demo-3min.audio.mp4"
    if not v3.exists():
        log(f"❌ 找不到 {v3}，先跑一次完整录制再 mux-only")
        return
    # 把带旧音频的版本备份（避免被覆盖丢东西）
    bak = v3.with_suffix(".noaudio.mp4")
    if not bak.exists():
        import shutil
        shutil.copy2(v3, bak)
        log(f"   备份无音频版: {bak.name}")
    # 抽视频流（扔掉旧音频轨）→ 临时文件
    tmp_v = out_dir / ".audio" / "video-only.mp4"
    tmp_v.parent.mkdir(parents=True, exist_ok=True)
    cmd = [str(FFMPEG_BIN), "-y", "-hide_banner", "-loglevel", "error",
           "-i", str(bak), "-an", "-c:v", "copy", str(tmp_v)]
    subprocess.run(cmd, check=True)
    log(f"   抽视频流: {tmp_v.name}")

    # 复用 add_audio_to_video 的 TTS + BGM + mux 流程
    add_audio_to_video(tmp_v, a3, TTS_ANCHORS,
                       storyboard_fn=storyboard, fps=args.fps)
    if a3.exists() and a3.stat().st_size > 1000:
        v3.unlink()
        a3.rename(v3)
        log(f"   已用音频版替换: {v3.name} ({v3.stat().st_size/1024/1024:.2f} MiB)")

    log("\nREADME 短版：")
    v1 = out_dir / "octosense-demo-1min30.mp4"
    a1 = out_dir / "octosense-demo-1min30.audio.mp4"
    if not v1.exists():
        log(f"❌ 找不到 {v1}，先跑一次完整录制再 mux-only")
        return
    bak1 = v1.with_suffix(".noaudio.mp4")
    if not bak1.exists():
        import shutil
        shutil.copy2(v1, bak1)
        log(f"   备份无音频版: {bak1.name}")
    tmp_v1 = out_dir / ".audio" / "video-only-1m30.mp4"
    cmd = [str(FFMPEG_BIN), "-y", "-hide_banner", "-loglevel", "error",
           "-i", str(bak1), "-an", "-c:v", "copy", str(tmp_v1)]
    subprocess.run(cmd, check=True)
    add_audio_to_video(tmp_v1, a1, TTS_ANCHORS,
                       storyboard_fn=readme_storyboard, fps=args.fps)
    if a1.exists() and a1.stat().st_size > 1000:
        v1.unlink()
        a1.rename(v1)
        log(f"   已用音频版替换: {v1.name} ({v1.stat().st_size/1024/1024:.2f} MiB)")
    log("\n✓ mux-only 完成")


def verify_bgm(args):
    """验证源 mp3 → make_bgm 切片+降音量，跑 5 秒样本。
    用法：放好 sunny-source.mp3 后跑 `python3 tools/record_demo.py --verify-bgm`。
    输出 .runtime/.audio/bgm-verify.wav，秒级完成。
    """
    log("=== verify-bgm ===")
    if not BENSOURCE_PATH.exists():
        log(f"❌ 源 mp3 不存在: {BENSOURCE_PATH}")
        log(f"   请把文件放到: {BENSOURCE_PATH}")
        return
    size = BENSOURCE_PATH.stat().st_size
    log(f"源 mp3: {BENSOURCE_PATH} ({size/1024/1024:.2f} MiB)")
    if size < 1024:
        log("❌ 源文件太小（<1KB），可能不是真 mp3。请检查是否下载失败。")
        return

    # 1. 读源 mp3 时长
    src_dur = get_audio_duration(BENSOURCE_PATH)
    log(f"源时长: {src_dur:.1f}s")
    if src_dur < 30:
        log("⚠️  源文件 < 30s，可能是剪辑/片段版（不是 Bensound 2:20 完整版）")

    # 2. 跑 make_bgm 生成 5 秒样本
    out = ROOT / ".runtime" / ".audio" / "bgm-verify.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    make_bgm(5.0, out)

    # 3. 验证输出
    if out.exists():
        out_dur = get_audio_duration(out)
        log(f"✓ 输出样本: {out} ({out.stat().st_size/1024:.1f} KB, {out_dur:.1f}s)")
        log("✓ BGM 路径可用，完整录制时会自动用源 mp3。")
        log(f"   播放: afplay {out}")
        log(f"   BG_VOL={BG_VOL}（已下调）")
    else:
        log("❌ make_bgm 没生成输出")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8932)
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--out-dir", default=str(ROOT / ".runtime"))
    ap.add_argument("--verify-bgm", action="store_true",
                    help="只验证源 mp3 → BGM 切片 + 音量，跑一个 5s 样本；不录制视频")
    ap.add_argument("--mux-only", action="store_true",
                    help="只重跑音频层（复用已有 mp4），不驱动 host、不重抓帧")
    args = ap.parse_args()

    if args.verify_bgm:
        verify_bgm(args)
        return
    if args.mux_only:
        mux_only(args)
        return

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    FRAME_DIR.mkdir(parents=True, exist_ok=True)

    # 1. 准备临时 bundle（剥签名）
    make_dev_bundle()
    p = boot_host(args.port)
    try:
        # 2. 抓所有剧情帧（hidden 步骤：name=None，不抓帧但跑 action）
        story = storyboard()
        log(f"开始抓帧：{len(story)} 段剧情")
        # 标题 / 结尾：纯合成图，不需要抓宿主截图
        # 其余：先跑 action，再从宿主抓真截图
        TITLE_CARDS = {"00_title.png", "99_outro.png"}
        for name, captions, action, hold in story:
            tag = name or "(hidden)"
            log(f"── {tag} ({hold}s) ──")
            if action is not None:
                action()
                time.sleep(1.5)
            if name is not None and name not in TITLE_CARDS:
                grab(args.port, FRAME_DIR / name)
                log(f"  saved {FRAME_DIR / name}")
            elif name in TITLE_CARDS:
                log(f"  (标题/结尾卡，不抓宿主)")
        # 兜底：检查 exported.ics 是否被保存（hidden 步骤应当已落盘）
        efile = FRAME_DIR / "exported.ics"
        if efile.exists():
            log(f"exported.ics: {efile.stat().st_size} bytes")
        else:
            log("WARN: exported.ics 未生成")
    finally:
        kill_host()

    # 3. 合成每张带字幕条的图（跳过 name=None 的 hidden 步骤）
    log("合成字幕条…")
    captioned = []
    for name, captions, action, hold in story:
        if name is None:
            continue
        if name in TITLE_CARDS:
            img = make_caption_card(captions if isinstance(captions, list) else [captions])
        else:
            cap = captions[0] if len(captions) == 1 else " · ".join(captions)
            cap_path = FRAME_DIR / f"{name}.captioned.png"
            composite_caption(FRAME_DIR / name, cap, cap_path)
            from PIL import Image
            img = Image.open(cap_path).convert("RGB")
        captioned.append((img, hold))

    # 4. 拼 3 分钟版
    log("\n=== 拼 3 分钟完整版 ===")
    compose_mp4(captioned, out_dir / "octosense-demo-3min.mp4", fps=args.fps)

    # 5. 拼 README 短版
    log("\n=== 拼 README 1 分钟版 ===")
    short = readme_storyboard()
    short_captioned = []
    for name, captions, action, hold in short:
        if name is None:
            continue
        if name in TITLE_CARDS:
            img = make_caption_card(captions if isinstance(captions, list) else [captions])
        else:
            cap = captions[0] if isinstance(captions, list) else captions
            cap_path = FRAME_DIR / f"{name}.captioned.png"
            composite_caption(FRAME_DIR / name, cap, cap_path)
            from PIL import Image
            img = Image.open(cap_path).convert("RGB")
        short_captioned.append((img, hold))
    compose_mp4(short_captioned, out_dir / "octosense-demo-1min30.mp4", fps=args.fps)

    # 6. 加音频层（背景 BGM + 关键节点 TTS 旁白）
    log("\n=== 加音频层（BGM + TTS 旁白）===")
    try:
        v3 = out_dir / "octosense-demo-3min.mp4"
        a3 = out_dir / "octosense-demo-3min.audio.mp4"
        log("3 分钟版：")
        add_audio_to_video(v3, a3, TTS_ANCHORS, storyboard_fn=storyboard, fps=args.fps)
        # 用音频版替换原版
        if a3.exists() and a3.stat().st_size > 1000:
            v3.unlink()
            a3.rename(v3)
            log(f"  已用音频版替换: {v3.name}")

        v1 = out_dir / "octosense-demo-1min30.mp4"
        a1 = out_dir / "octosense-demo-1min30.audio.mp4"
        log("README 短版：")
        add_audio_to_video(v1, a1, TTS_ANCHORS, storyboard_fn=readme_storyboard, fps=args.fps)
        if a1.exists() and a1.stat().st_size > 1000:
            v1.unlink()
            a1.rename(v1)
            log(f"  已用音频版替换: {v1.name}")
    except Exception as e:
        log(f"  音频层失败（非致命，视频仍可用）：{e}")
        import traceback
        traceback.print_exc()

    # 7. 清理
    cleanup_dev_bundle()
    log("\n✓ 全部完成")


if __name__ == "__main__":
    main()