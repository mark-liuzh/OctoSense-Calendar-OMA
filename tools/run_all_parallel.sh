#!/usr/bin/env bash
# OctoSense 全量回归 · 并行版
#
#   bash tools/run_all_parallel.sh            # 静态自检 + 8 条端到端流程（默认并发 4）
#   bash tools/run_all_parallel.sh --fast     # 只跑静态自检（不启动宿主，秒级）
#   bash tools/run_all_parallel.sh --jobs 2   # 指定并发数（建议 2–4）
#
# 说明：
# - 串行版 run_all.sh 仍保留，作为稳定兜底。
# - 并行版为每条流程分配独立端口、独立存储目录、独立 evidence 目录，
#   并通过 HOST_PID 精确清理本流程的 card-host，避免互相踩踏。
# - 默认并发 4：在本机 Apple Silicon 上 8 条流程总耗时约 2–3 分钟；
#   Windows / 低配机器建议 --jobs 2。
# - 若出现偶发假失败（截图时窗口被抢焦点等），先降到 --jobs 1 复现，
#   确认不是并行引入的噪声后再追根因。
#
# 退出码：0 = 全过；非 0 = 失败流程数。
set -u
cd "$(dirname "$0")/.."
ROOT="$PWD"
OUT="$ROOT/.runtime"
mkdir -p "$OUT"

FAST=0
JOBS=4
while [ $# -gt 0 ]; do
  case "$1" in
    --fast) FAST=1; shift ;;
    --jobs) JOBS="${2:-4}"; shift 2 ;;
    --jobs=*) JOBS="${1#*=}"; shift ;;
    *) echo "未知参数: $1" >&2; exit 2 ;;
  esac
done

# shellcheck source=tools/_env.sh
. "$ROOT/tools/_env.sh"

# 若 _env.sh 没探测到 card-host，补充本仓库实际布局（_toolchain/）。
if [ -z "${HOST:-}" ]; then
  for cand in "$ROOT/_toolchain/OctoSense-App-Hub/target/release/card-host" \
              "$ROOT/_toolchain/OctoSense-App-Hub/target/release/card-host.exe"; do
    [ -x "$cand" ] && HOST="$cand" && break
  done
fi
if [ -z "${HOST:-}" ]; then
  echo "FATAL: 找不到 card-host。" >&2
  echo "       请设置 OCTO_CARD_HOST=/path/to/card-host 后重跑。" >&2
  exit 2
fi
export HOST

LOGDIR="$OUT/run-all-parallel"
mkdir -p "$LOGDIR"

STAMP="$(date +%s)"
BASE_PORT=8932

STEPS="run_e2e run_conflict run_edge run_negative run_festival run_layout run_new run_features"

echo "=================================================================="
echo "OctoSense 全量回归（并行版） $(date '+%Y-%m-%d %H:%M:%S')"
echo "python:    $PY"
echo "card-host: ${HOST:-（未探测；--fast 模式不启动宿主）}"
echo "并发数:    ${JOBS}"
echo "日志:      ${LOGDIR}"
echo "模式:      $([ "$FAST" = 1 ] && echo '仅静态自检' || echo '静态自检 + 8 条端到端流程')"
echo "=================================================================="

# ── 阶段 1：静态自检（串行，秒级）───────────────────────────────────────
echo
echo "######## 阶段 1/2 · 静态自检 ########"
static_gate
for t in brace quotes toplevel deps paintfix btnfocus cellhover fncalls; do
  printf '  %-10s ' "$t"
  if out=$("$PY" "$ROOT/tools/$t.py" "$ROOT/${BUNDLE:-bundle}/main.splash" 2>&1); then
    echo "PASS"
  else
    echo "FAIL"
    printf '%s\n' "$out" | tail -10
    exit 1
  fi
done

if [ "$FAST" = 1 ]; then
  echo
  echo "（--fast：跳过端到端流程）"
  echo "全量回归 PASS（仅静态）"
  exit 0
fi

# ── 阶段 2：端到端流程（并发）───────────────────────────────────────────
echo
echo "######## 阶段 2/2 · 端到端流程（并发 ${JOBS}）########"

# 结果汇总
FAILED=""
FAILED_PREREQ=""
NOK=0
NFAIL=0

# 任务队列文件
queue_file="$LOGDIR/.queue"
rm -f "$queue_file"
for s in $STEPS; do echo "$s"; done > "$queue_file"

# 每个运行中的任务一个目录，里面放 pid / step / rc
jobs_dir="$LOGDIR/.jobs"
rm -rf "$jobs_dir"
mkdir -p "$jobs_dir"

cleanup_all() {
  # 收到中断信号时，把还在跑的子流程全部杀掉
  for d in "$jobs_dir"/*; do
    [ -d "$d" ] || continue
    pid=$(cat "$d/pid" 2>/dev/null || true)
    [ -n "$pid" ] && kill "$pid" 2>/dev/null || true
  done
}
trap cleanup_all INT TERM

start_next() {
  local s
  s=$(head -1 "$queue_file")
  [ -n "$s" ] || return 1
  # 从队列移除
  tail -n +2 "$queue_file" > "$queue_file.tmp" && mv "$queue_file.tmp" "$queue_file"

  local port=$((BASE_PORT + next_port_offset))
  next_port_offset=$((next_port_offset + 1))
  local app_data="$OUT/app-data-parallel-$s-$STAMP"
  local ev="$OUT/evidence-parallel-$s"
  local logf="$LOGDIR/$s.txt"
  local job_dir="$jobs_dir/$s"
  mkdir -p "$job_dir"
  echo "$s" > "$job_dir/step"

  echo
  echo ">>> $s (PORT=${port}, APP_DATA=${app_data})"

  (
    cd "$ROOT"
    export PORT="$port"
    export OCTO_PORT="$port"
    export APP_DATA="$app_data"
    export EV="$ev"
    # 禁用代理，避免子流程复用父 shell 的 http_proxy 干扰本地控制桥
    export NO_PROXY="127.0.0.1,localhost${NO_PROXY:+,}$NO_PROXY"
    export no_proxy="$NO_PROXY"
    bash "$ROOT/tools/$s.sh" > "$logf" 2>&1
    echo $? > "$job_dir/rc"
  ) &

  echo $! > "$job_dir/pid"
  return 0
}

# 全局计数器：下一个任务使用哪个端口偏移
next_port_offset=0

# 初始启动一批
for _ in $(seq 1 "$JOBS"); do
  start_next || break
done

# 等待并补充
while [ -n "$(ls -A "$jobs_dir" 2>/dev/null)" ]; do
  found=0
  for d in "$jobs_dir"/*; do
    [ -d "$d" ] || continue
    s=$(cat "$d/step" 2>/dev/null || true)
    pid=$(cat "$d/pid" 2>/dev/null || true)
    [ -n "$s" ] || continue
    [ -n "$pid" ] || continue

    # 已结束：rc 文件已写，或进程不存在
    if [ -f "$d/rc" ] || ! kill -0 "$pid" 2>/dev/null; then
      found=1
      if [ -f "$d/rc" ]; then
        rc=$(cat "$d/rc")
      else
        wait "$pid"
        rc=$?
      fi
      rm -rf "$d"

      echo "  -> $s exit=${rc}   （完整日志 ${LOGDIR}/$s.txt）"
      grep -E "PASS|FAIL|FATAL|错误数|前置检查|存储目录|断言通过" "$LOGDIR/$s.txt" 2>/dev/null | tail -12 | sed 's/^/    /'

      if [ "$rc" = "0" ]; then
        NOK=$((NOK + 1))
      elif [ "$rc" = "2" ]; then
        FAILED_PREREQ="$FAILED_PREREQ $s"
        NFAIL=$((NFAIL + 1))
      else
        FAILED="$FAILED $s"
        NFAIL=$((NFAIL + 1))
      fi

      # 补充新任务
      start_next || true
      break
    fi
  done

  if [ "$found" = "0" ]; then
    sleep 0.5
  fi
done

trap - INT TERM

# ── 汇总 ──────────────────────────────────────────────────────────────
_n_list() { local n=0 w; for w in $1; do n=$((n + 1)); done; printf '%s' "$n"; }
N_HARD=$(_n_list "$FAILED")
N_PRE=$(_n_list "$FAILED_PREREQ")

echo
echo "=================================================================="
echo "汇总：通过 $NOK / $((NOK + NFAIL))"
echo "应用/断言失败（**结论有效**）: $N_HARD 条${FAILED:+ }$FAILED"
if [ "$N_PRE" != "0" ]; then
  echo "前置/夹具失败（**脚本缺陷，本次不作应用结论**）: $N_PRE 条$FAILED_PREREQ"
  echo "  ↑ 这些流程在断言跑起来之前就中止了，列出的是**根因所在**而不是症状。"
  echo "    请只看上面「应用/断言失败」那一行判断应用好坏。"
else
  echo "前置/夹具失败（**脚本缺陷，本次不作应用结论**）: 0 条"
fi
if [ "$NFAIL" != "0" ]; then
  echo "失败合计: $NFAIL${FAILED:+ }$FAILED${FAILED_PREREQ:+ }$FAILED_PREREQ"
  echo "=================================================================="
  exit "$NFAIL"
fi
echo "全量回归 PASS"
echo "=================================================================="
exit 0
