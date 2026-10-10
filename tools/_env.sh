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

# ⚠️ card-host 不存在时的报错**不能放在 _env.sh 顶层**（2026-10-02 修复）：
#    否则 `bash tools/run_all.sh --fast` 会在 source 到这一行时直接 exit 1，
#    连 static_gate 都跑不到，README 里「只跑静态自检、秒级」的承诺变成空话。
#    探测本身（上面那一段）保留无害（找到就赋值，找不到就让 HOST 保持空）。
#    真正需要 HOST 的入口（boot_host）在函数开头自己检查并退出。

# ── 编码 ──────────────────────────────────────────────────────────────
# ⚠️ Windows 上 Python 的 stdout 默认跟随本地代码页（cp936）。脚本里到处是
#    中文断言串（「放假 3 天」「节日 中国」…），一旦 python 侧用 cp936 编码、
#    外层用 UTF-8 解码，`grep` 就永远匹配不上，而且报错信息是乱码，极难定位。
#    统一钉死 UTF-8，脚本内容与输出用同一套编码。
export PYTHONIOENCODING="utf-8"
export PYTHONUTF8="1"

# ── bundle 路径（可覆盖）───────────────────────────────────────────────
# 默认就是提交件bundle/。若本机card-host 跑不起来（它内置 RefuseAllSignatures，
# 对**任何**带签名的 manifest 一律拒绝，而 OMA 公钥只在提交 App Hub 那侧安装），
# 可用 OCTO_BUNDLE 指向一份剥掉 integrity.signature 的**副本**：
#   python3 -c "import sys;sys.path.insert(0,'tools');import record_demo as R;R.make_dev_bundle()"
#   OCTO_BUNDLE=.runtime/bundle-dev bash tools/run_all.sh
# ⚠️ 绝不要因此改 bundle/manifest.json 的integrity，也不要用本机 `hub stamp`
#    修 digest —— 那会让仓库与发布件分叉（见 docs/RELEASE-NOTES-v0.4.1.md §7）。
BUNDLE="${OCTO_BUNDLE:-bundle}"

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

# ── 静态门禁 ──────────────────────────────────────────────────────────
# 每轮端到端之前先跑一遍静态检查，任何一项不过就直接退出 ——
# 免得带着语法/规则错误去跑十分钟的界面流程，最后只看到一堆对不上的断言。
#   brace    括号配平
#   quotes   引号配对
#   toplevel 顶层只允许 fn / let / 一条 start_timeout
#   deps     建树时求值的前向引用（函数体内前向引用是安全的，不报）
#   paintfix 「画背景必须用 RoundedView / CircleView / SolidView」规则门禁
#   btnfocus 每个 ButtonFlat 必须显式写 color_focus（否则点一下就「消失」）
#   cellhover 月历点击层必须是**半透明**状态色（否则悬停糊掉日期数字）
#   fncalls  **调用了但从未定义**的函数名（2026-10-01 新增）
#            —— 这一道是补一个具体伤口：新功能版里 `heat_of` / `todo_count`
#               被调用却根本没写，deps 抓不到（它们只在运行时上下文里出现），
#               静态语法也合法，只有真跑才炸，而且报错离真因隔了三层
#               （on_render 报错 → 月历空白 → refresh_all 中断 → assert_clean
#                误报「存储不干净」）。
static_gate() {
  local f="$ROOT/$BUNDLE/main.splash" rc=0 out t
  for t in brace quotes toplevel deps paintfix btnfocus cellhover fncalls; do
    if ! out=$("$PY" "$ROOT/tools/$t.py" "$f" 2>&1); then
      echo "FATAL: 静态门禁 tools/$t.py 未通过：" >&2
      printf '%s\n' "$out" | tail -20 >&2
      rc=1
    fi
  done
  # ★ 2026-10-10（v0.5.0）：AI 改期层的七道闸判定夹具。
  #   为什么它属于 static_gate：`model.complete` 的**成功路径**本机验不了
  #   （card-host 不注册该服务，真机又要求先提交进商店），所以闸门逻辑本身
  #   就是唯一能在本机持续验的部分。它是纯 Python、秒级、不起宿主。
  #   `--sync` 额外把 13 条拒绝理由与 bundle 的 ai_verify 逐字比对 ——
  #   夹具是复刻的，漂了就等于在验一份和实现不同的规则（假绿）。
  if ! out=$("$PY" "$ROOT/tools/test_ai_gates.py" --sync "$f" 2>&1); then
    echo "FATAL: AI 闸门夹具 tools/test_ai_gates.py 未通过：" >&2
    printf '%s\n' "$out" | tail -20 >&2
    rc=1
  fi
  [ "$rc" = "0" ] || exit 1
  echo "静态门禁: brace / quotes / toplevel / deps / paintfix / btnfocus / cellhover / fncalls / ai_gates 全过"
}

# ── 前置检查：应用存储必须是干净的 ────────────────────────────────────
# 所有端到端流程都假设「空事件库」起步。若上一轮宿主的存储没被清掉，
# 日历里会凭空多出日程点，断言会对不上，而且报错信息完全指不到真正的原因。
#
# ★ 2026-10-03 Windows 兼容补丁：原本单次 texts 期望「已加载 0 个事件」，
#   Apple silicon macOS 上 splash 1.5 秒就能画完第一帧，断言立刻 PASS。
#   Windows 裸机上 splash 首次 eval (334 KB) 走 font-atlas + 编译，
#   通常 4-6 秒才完成 —— 单次 texts 拿到的是 card-host 控制桥 UI（"Card host [remote]"），
#   永远看不到「已加载 0 个事件」。改为轮询 15 次（间隔 0.7s），单跑不阻塞，全跑不破。
assert_clean() {
  local t i
  for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
    t=$("$PY" "$ROOT/tools/e2e.py" texts 2>&1)
    case "$t" in
      *"已加载 0 个事件"*)
        echo "前置检查: 存储干净（0 个事件）"
        return 0 ;;
    esac
    sleep 0.7
  done
  echo "FATAL: 应用存储不干净，预期「已加载 0 个事件」。实际末尾：" >&2
  printf '%s\n' "$t" | tail -2 >&2
  exit 1
}

# ── 宿主日志里的编译/运行错误数 ───────────────────────────────────────
# ⚠️ 不能写 `$(grep -c ... || echo 0)`：grep -c 无匹配时**自己会输出 0**
#    且退出码为 1，于是 `|| echo 0` 再补一个 0 → 结果是两行 "0\n0"。
#    后果有两个：屏幕上多出一个来路不明的 0（看着像别的什么东西坏了），
#    以及任何 `[ "$n" = "0" ]` 比较都会**假失败**（2026-09-30 踩到）。
host_error_count() {
  local n
  # ⚠️ 不要写 `$(grep -c ... || echo 0)`：grep -c 无匹配时**自己会输出 0**
  #    且退出码为 1，于是 `|| echo 0` 再补一个 0 → 结果是两行 "0\n0"。
  #    后果有两个：屏幕上多出一个来路不明的 0（看着像别的什么东西坏了），
  #    以及任何 `[ "$n" = "0" ]` 比较都会**假失败**（2026-09-30 踩到）。
  n=$(grep -c '\[E\]' "$1" 2>/dev/null || true)
  n=${n:-0}
  # ★ 2026-10-08（P0-4）：过滤**良性降级**白名单。
  #    Linux 上没有 PulseAudio 服务端时，makepad 会打 error 级日志再回退 ALSA
  #    继续运行（platform/src/os/linux/pulse_audio.rs:740-753：PA_CONTEXT_NOAUSPAWN
  #    下连不上 → 打日志 → 销毁 context → return None）。降级成功，不是崩溃，
  #    但它会让「编译/运行错误数 = 0」这条硬指标在 Linux 上永远为 1。
  #    本应用 bundle/main.splash 音频 API 引用实测 0 处（display_list 会误命中，
  #    排除后为 0），根本走不到这条路径 —— 纯属宿主环境噪声。
  if [ "$n" != "0" ] && [ -n "${HOST_ERROR_WHITELIST:-}" ]; then
    n=$(grep '\[E\]' "$1" 2>/dev/null | grep -vE "$HOST_ERROR_WHITELIST" | grep -c '' || true)
    n=${n:-0}
  fi
  printf '%s' "$n"
}

# 白名单：Linux 无声卡环境下宿主自报的良性降级（不算应用错误）
HOST_ERROR_WHITELIST='pulse_audio\.rs:.*pa_context_connect failed|pulseaudio.*connection refused|ALSA fallback'

# ── 宿主进程探测 ──────────────────────────────────────────────────────
# 实测：本机 `tasklist` 可用，输出里进程名就是 `card-host.exe`（不带路径）。
# 注意 `grep -c` 在这个环境里对中文表头没问题，唯一要防的是「tasklist 本身失败」
# （沙箱下偶发）—— 那种情况按「探测不到」处理，交给调用方的重试与端口校验兜底。
host_pids() {
  command -v tasklist >/dev/null 2>&1 || return 0
  tasklist 2>/dev/null | grep -i "card-host.exe" || true
}

host_running() {
  [ -n "$(host_pids)" ]
}

# ── 收工：结束宿主（Windows 与 POSIX 都能用）─────────────────────────
# ⚠️ 必须**确认**进程真的退了才返回（2026-09-30 踩过两次）：
#    宿主没退干净 → 存储目录/端口仍被占用 →
#      · 原地 `rm -rf` 静默失败 → 下一轮带着**上一轮的事件**开跑，
#        日历里凭空多出日程点，而布局树断言全过（数据是异步 load 的），极难定位；
#      · 新宿主绑不上端口 → 就绪探测却打到了**旧宿主**身上，全程测的是上一轮的进程。
#    所以这里：杀 → 轮询确认消失 → 不行就再来一轮，共 3 轮；仍失败则打印 PID 清单。
kill_host() {
  local round i
  for round in 1 2 3; do
    if command -v taskkill >/dev/null 2>&1; then
      # //T 连子进程一起杀；没有子进程时也不报错
      taskkill //F //T //IM card-host.exe >/dev/null 2>&1 || true
    fi
    if command -v pkill >/dev/null 2>&1; then
      pkill -f card-host >/dev/null 2>&1 || true
    fi
    for i in $(seq 1 20); do
      host_running || return 0
      sleep 0.3
    done
  done
  echo "WARN: card-host 仍在运行（已重试 3 轮），PID 清单：" >&2
  host_pids >&2
  return 1
}

# ── 端口占用探测 ──────────────────────────────────────────────────────
# 宿主就绪探测只看「端口有没有响应」。若上一个宿主没退干净，新宿主绑不上端口，
# 但**探测会打到旧宿主**上——于是整轮测试其实是在测别人的进程，结果全错却不自知。
# 所以启动前先确认端口是空的。
port_busy() {
  $CURL --max-time 3 "http://127.0.0.1:$PORT/" >/dev/null 2>&1
}

# ── 每次运行一个全新的私有存储目录 ────────────────────────────────────
# 见 boot_host 里的说明：不依赖「能否删掉上一轮的目录」。
APP_DATA=""

# ── 启动宿主并等它就绪 ────────────────────────────────────────────────
# $1 = 日志文件路径
# $2 = 可选。**复用**某个已有的 app-data 目录（用于「重启后数据还在吗」这类断言）。
#      ★ 2026-10-01 新增：默认行为一点没变（每次全新目录），只有显式传目录时才复用。
#        为什么需要它：用户的硬要求是「离线可用、本地优先存储」。要证明这一点，
#        唯一有说服力的方式是「进程没了 → 新进程把数据读回来」。而在同一个宿主
#        进程里读内存数组，从来没坏过 —— 那不构成证据。
#      ⚠️ 复用时**不能**去回收旧目录（下面那句 find -exec rm 会把它自己删掉）。
boot_host() {
  local log="$1"
  local reuse="${2:-}"

  # ★ 2026-10-02 修复：card-host 必需性检查**移到真正启动宿主时**。
  #    原来放在 _env.sh 顶层会让 `bash tools/run_all.sh --fast` 在 source 阶段
  #    就被拦死，根本进不到 static_gate。详见函数定义处的注释。
  if [ -z "${HOST:-}" ]; then
    echo "FATAL: 找不到 card-host。" >&2
    echo "       先构建：cd OctoSense-App-Hub && cargo build --release -p octosense-card-host -p octosense-app-hub" >&2
    echo "       或指定：OCTO_CARD_HOST=/path/to/card-host bash tools/run_e2e.sh" >&2
    exit 1
  fi

  kill_host

  # ⚠️ 不要用「原地清空 .runtime/app-data」这一招（2026-09-30 定案）。
  #    它把整轮测试的正确性押在「上一轮的宿主已经彻底退出、且 Windows 已释放
  #    文件句柄」这一件事上。Windows 上这个前提经常不成立（杀进程后句柄延迟
  #    释放、杀毒/索引器短暂占用、僵尸宿主），而 `rm -rf ... 2>/dev/null || true`
  #    会把失败**吞掉**：下一轮就带着上一轮的事件开跑，日历里凭空多出日程点，
  #    布局树断言却全过（数据是异步 load 进来的），只有像素断言对不上。
  #    ⇒ 改成**每轮换一个全新的存储目录**，旧的尽力删。删不掉也不影响本轮，
  #      整条依赖就此消除。
  if [ -n "$reuse" ] && [ -d "$reuse" ]; then
    APP_DATA="$reuse"
  else
    local stamp
    stamp="$(date +%s)-$$"
    APP_DATA="$OUT/app-data-$stamp"
    rm -rf "$APP_DATA" 2>/dev/null || true
    mkdir -p "$APP_DATA" || true

    # 尽力回收历史目录（含旧的 app-data / probe）。删不掉无所谓，不阻塞本轮。
    find "$OUT" -maxdepth 1 -type d -name 'app-data-*' ! -path "$APP_DATA" \
      -exec rm -rf {} + 2>/dev/null || true
    rm -rf "$OUT/app-data" "$OUT/probe" 2>/dev/null || true
  fi

  # 启动前先确认端口是空的 —— 否则新宿主绑不上，探测却打到旧宿主身上，
  # 整轮测试其实在测别人的进程。
  if port_busy; then
    echo "FATAL: 端口 $PORT 已有响应，说明上一个宿主没退干净。" >&2
    echo "       仍在运行的 card-host：" >&2
    host_pids >&2
    echo "       修法：taskkill /F /IM card-host.exe 后重跑。" >&2
    exit 1
  fi

  # ⚠️⚠️ 显式传 --size（2026-10-08）：不传时 card-host 默认 412x892，但实测
  #   `main_window r=[0,0,412,849]` —— 少了 43px。后果不是「窗口小一点」那么温和：
  #   竖向预算被挤爆后 tools 容器从 56px（12+32+12）塌成 31px，
  #   三个按钮的 height 从 32 被压到 **14~16px**，点「导入」不响应
  #   （`open` 报「entry 不在树里」），状态条「已加载 0 个事件」也换行被裁
  #   ⇒ assert_clean 直接 FATAL，整条流程根本开不了局。
  #   ⚠️ 这与显示器分辨率无关、也与本轮改动无关（git stash 回 HEAD 原版同样复现），
  #   是宿主在本机的窗口高度协商行为。显式给一个更宽松的高度即可绕开：
  #   实测 --size 412x1000 时按钮恢复 32px、「已加载 0 个事件」正常出现。
  #   892 是 bundle 的设计视口，给更高只是让它有余量，不会改变布局。
  MAKEPAD_REMOTE="$PORT" "$HOST" --bundle "$BUNDLE" --app-data "$APP_DATA" \
    --size "${WINDOW_SIZE:-412x1000}" --allow-unsigned --stamp > "$log" 2>&1 &
  local ready=0
  for _ in $(seq 1 20); do
    if $CURL --max-time 3 "http://127.0.0.1:$PORT/" >/dev/null 2>&1; then ready=1; break; fi
    sleep 1
  done
  if [ "$ready" != "1" ]; then
    echo "FATAL: 宿主未就绪。日志尾部：" >&2
    tail -20 "$log" >&2
    host_running && { echo "       仍在运行的 card-host：" >&2; host_pids >&2; }
    exit 1
  fi
  sleep 2
  # 本轮用的是哪个存储目录 —— 排障时最想知道的一件事。
  echo "存储目录: $APP_DATA"
}
