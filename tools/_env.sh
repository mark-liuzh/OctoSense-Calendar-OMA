#!/usr/bin/env bash
# OctoSense 实测脚本共用的环境探测。由 run_e2e.sh / run_conflict.sh source。
#
# 覆盖方式（全部可选）：
#   PY=<python 可执行文件>        默认自动找 python3 / python
#   OCTO_CARD_HOST=<card-host>   默认按官方顺序在常见构建目录里找
#   PORT=<端口>                  默认 8932
#
# 找不到就明确报错并给出修法，而不是让脚本跑到一半才炸。

# ── python ────────────────────────────────────────────────────────────
if [ -z "${PY:-}" ]; then
  for c in python3 python; do
    if command -v "$c" >/dev/null 2>&1; then PY="$c"; break; fi
  done
fi
if [ -z "${PY:-}" ]; then
  echo "FATAL: 找不到 python3（脚本用 Python 3.9+，无第三方依赖）。" >&2
  echo "       修法：安装 Python，或 PY=/path/to/python bash tools/run_e2e.sh" >&2
  exit 1
fi

# ── card-host（与官方 tools/octo 相同的搜索顺序 + 本仓库的构建目录）──
_host_candidates() {
  [ -n "${OCTO_CARD_HOST:-}" ]     && printf '%s\n' "$OCTO_CARD_HOST"
  [ -n "${OCTOSENSE_APP_HUB:-}" ]  && printf '%s\n' "$OCTOSENSE_APP_HUB/target/release/card-host"
  [ -n "${CARGO_TARGET_DIR:-}" ]   && printf '%s\n' "$CARGO_TARGET_DIR/release/card-host"
  # 仓库与 App Hub 是兄弟目录（官方工作区布局）
  printf '%s\n' "$ROOT/../OctoSense-App-Hub/target/release/card-host"
  printf '%s\n' "$ROOT/../.cargo-target/octosense/release/card-host"
  # 仓库在 Apps/ 下一层时的布局（本项目的实际布局）
  printf '%s\n' "$ROOT/../../OctoSense-App-Hub/target/release/card-host"
  printf '%s\n' "$ROOT/../../.cargo-target/octosense/release/card-host"
  command -v card-host 2>/dev/null || true
  return 0
}

if [ -z "${HOST:-}" ]; then
  while IFS= read -r cand; do
    [ -n "$cand" ] || continue
    for p in "$cand" "$cand.exe"; do
      if [ -x "$p" ]; then HOST="$p"; break 2; fi
    done
  done <<EOF
$(_host_candidates)
EOF
fi

if [ -z "${HOST:-}" ]; then
  echo "FATAL: 找不到 card-host。" >&2
  echo "       先构建：cd OctoSense-App-Hub && cargo build --release -p octosense-card-host -p octosense-app-hub" >&2
  echo "       或指定：OCTO_CARD_HOST=/path/to/card-host bash tools/run_e2e.sh" >&2
  exit 1
fi

# ── 端口 ──────────────────────────────────────────────────────────────
PORT="${PORT:-8932}"
export OCTO_PORT="$PORT"   # tools/e2e.py 读这个

# ── 代理 ──────────────────────────────────────────────────────────────
# ⚠️ 宿主的远程控制桥跑在 127.0.0.1 上。若 shell 里设了 http_proxy（常见于
#    挂代理的机器），本地请求也会被送进代理 → 502 Bad Gateway，或拿到上一帧
#    的陈旧截图，症状是「截图与步骤对不上、点击像没生效」。必须显式绕过。
export NO_PROXY="127.0.0.1,localhost${NO_PROXY:+,$NO_PROXY}"
export no_proxy="$NO_PROXY"
CURL="curl -s --noproxy 127.0.0.1 --max-time 20"

# ── 收工：结束宿主（Windows 与 POSIX 都能用）─────────────────────────
kill_host() {
  if command -v taskkill >/dev/null 2>&1; then
    taskkill //F //IM card-host.exe >/dev/null 2>&1 || true
  fi
  pkill -f card-host >/dev/null 2>&1 || true
}

# ── 启动宿主并等它就绪 ────────────────────────────────────────────────
# $1 = 日志文件路径
boot_host() {
  local log="$1"
  kill_host
  sleep 1
  rm -rf "$OUT/app-data"
  mkdir -p "$OUT/app-data"
  MAKEPAD_REMOTE="$PORT" "$HOST" --bundle bundle --app-data "$OUT/app-data" \
    --allow-unsigned --stamp > "$log" 2>&1 &
  local ready=0
  for _ in $(seq 1 20); do
    if $CURL --max-time 3 "http://127.0.0.1:$PORT/" >/dev/null 2>&1; then ready=1; break; fi
    sleep 1
  done
  if [ "$ready" != "1" ]; then
    echo "FATAL: 宿主未就绪。日志尾部：" >&2
    tail -20 "$log" >&2
    exit 1
  fi
  sleep 2
}
