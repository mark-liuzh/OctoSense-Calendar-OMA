#!/usr/bin/env bash
# OctoSense 全量回归 · 一条命令跑完所有自检与端到端流程
#
#   bash tools/run_all.sh            # 静态自检 + 8 条端到端流程
#   bash tools/run_all.sh --fast     # 只跑静态自检（不启动宿主，秒级）
#
# 每条流程**串行**执行，且每条都以「宿主已收工」结束 —— 串行是刻意的：
# 它们共用同一个远程控制端口与宿主进程，并行会互相踩。
#
# ⚠️ 为什么需要一个固定脚本、而不是临时写个 for 循环（2026-09-30）：
#    串行跑法的正确性完全押在「每条流程结束时宿主真的退了」上。一旦某条流程
#    漏了收工，失败会**出现在下一条**（端口被占/存储清不掉），报错信息与
#    真正的原因隔了一层，排查成本极高（已误伤一次）。所以这里显式做两件事：
#      1. 每条流程跑完，主动再 kill_host 一次兜底，并校验端口已释放；
#      2. 每条流程开跑前，确认没有僵尸宿主。
#
# 退出码：0 = 全过；非 0 = 失败流程数。
set -u
cd "$(dirname "$0")/.."
ROOT="$PWD"
OUT="$ROOT/.runtime"
mkdir -p "$OUT"

FAST=0
[ "${1:-}" = "--fast" ] && FAST=1

# shellcheck source=tools/_env.sh
. "$ROOT/tools/_env.sh"

LOGDIR="$OUT/run-all"
mkdir -p "$LOGDIR"

echo "=================================================================="
echo "OctoSense 全量回归   $(date '+%Y-%m-%d %H:%M:%S')"
echo "python:    $PY"
echo "card-host: ${HOST:-（未探测；--fast 模式不启动宿主）}"
echo "端口:      $PORT"
echo "模式:      $([ "$FAST" = 1 ] && echo '仅静态自检' || echo '静态自检 + 8 条端到端流程')"
echo "=================================================================="

# ── 阶段 1：静态自检 ──────────────────────────────────────────────────
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

# ── 阶段 2：端到端流程 ────────────────────────────────────────────────
# 顺序固定：基本 → 冲突消解 → 边界/往返 → 负例 → 节假日 → 布局几何。
# 前一条是后一条的前提（例如节假日流程假设存储为空、事件库可由脚本自造）。
# ⚠️ run_new 放在最后：它建的是「手工事件」，前半段断言依赖事件库为空。
# ★ run_features 排在 run_new 之后（2026-10-01）：它覆盖的是**非日程**的六个分区
#   （待办/心情/目标/彩蛋/视图/吉祥物/胶囊），与前七条几乎不共享状态；
#   放在最后，即便它整条挂了也不会污染前面的断言。
# ★ run_new_features 排在最后（2026-10-13 P2-5）：它覆盖 v0.5.6 新功能
#   （历史回滚 / 取消后自动释放），自建事件、自带重启验证，不与前八条共享状态。
STEPS="run_e2e run_conflict run_edge run_negative run_festival run_layout run_new run_features run_new_features"

FAILED=""
FAILED_PREREQ=""     # exit=2：前置/夹具失败，**后续断言没跑完**，不代表应用坏
NFAIL=0
NOK=0

echo
echo "######## 阶段 2/2 · 端到端流程 ########"

for s in $STEPS; do
  echo
  echo "------------------------------------------------------------------"
  echo ">>> $s"
  echo "------------------------------------------------------------------"

  # 前置：确认没有僵尸宿主占着端口
  if port_busy; then
    echo "  发现端口 $PORT 仍被占用，先清理僵尸宿主"
    kill_host || true
    if port_busy; then
      echo "  FATAL: 端口 $PORT 仍被占用，无法继续。仍存活的 card-host："
      host_pids
      FAILED="$FAILED $s(前置)"
      NFAIL=$((NFAIL + 1))
      continue
    fi
  fi

  logf="$LOGDIR/$s.txt"
  if bash "$ROOT/tools/$s.sh" > "$logf" 2>&1; then
    rc=0
  else
    rc=$?
  fi

  # 收工兜底：无论流程自己有没有收好，这里再杀一次并确认端口释放。
  kill_host >/dev/null 2>&1 || true
  if port_busy; then
    echo "  WARN: $s 结束后端口 $PORT 仍有响应（$s 可能漏了 kill_host）"
  fi

  # 摘要：把关键几行摊出来，不完整的日志留在 .runtime/run-all/ 下
  grep -E "PASS|FAIL|FATAL|错误数|前置检查|存储目录|断言通过" "$logf" | tail -12 | sed 's/^/  /'
  echo "  -> $s exit=$rc   （完整日志 .runtime/run-all/$s.txt）"

  if [ "$rc" = "0" ]; then
    NOK=$((NOK + 1))
  elif [ "$rc" = "2" ]; then
    # ★ 2026-10-12（v0.5.2 W1-5）：退出码 2 = **前置/夹具失败**（must_drive /
    #    assert_clean / boot_host 的 FATAL）。它意味着「这条流程的断言根本没跑完」，
    #    而不是「应用断言不通过」。
    #    为什么要单独归类：v0.5.1 及以前两类都算「失败」，汇总只有一句
    #    「失败：run_e2e run_new」—— 读起来像应用全面崩了，其实真应用失败是 0 条，
    #    全是脚本在 Linux/Windows 上找不到 octo、点不开面板造成的连锁红
    #    （Linux 报告 run_new 10 条红 / Windows 报告 7/8 条红都是这个）。
    FAILED_PREREQ="$FAILED_PREREQ $s"
    NFAIL=$((NFAIL + 1))
  else
    FAILED="$FAILED $s"
    NFAIL=$((NFAIL + 1))
  fi
done

# ── 汇总 ──────────────────────────────────────────────────────────────
_n_list() { local n=0 w; for w in $1; do n=$((n + 1)); done; printf '%s' "$n"; }
N_HARD=$(_n_list "$FAILED")
N_PRE=$(_n_list "$FAILED_PREREQ")

echo
echo "=================================================================="
echo "汇总：通过 $NOK / $((NOK + NFAIL))"
# 必须先把「几条是真应用失败、几条是脚本自身缺陷」说清楚，再给总数。
# 只给一个「通过 3/8」的话，读的人无从判断这次结果能不能拿去做验收 ——
# 这正是两份测试报告最被误读的地方。
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
