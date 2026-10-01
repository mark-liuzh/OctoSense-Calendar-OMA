#!/usr/bin/env bash
# OctoSense 商店截图生成（写入 bundle/screenshots/）
#
# 为什么单独一个脚本：listing.json 里引用的 12 张截图必须是**实机截取**，
# 界面一改就得重出，所以把「怎么摆出这 12 个状态」固化下来，而不是靠手工点。
#
# 07 / 08 两步顺带是一条回归：**三个面板必须互斥**。
#   「新建面板开着再点关于」→ 关于页要能正常打开（否则底部按钮被挤出视口）；
#   「关于页开着再点回」→ 新建面板要能正常打开。toggle 里漏写一句互斥就会炸。
#
# 用法: bash tools/shots.sh
# 可选: PY=<python>  OCTO_CARD_HOST=<card-host>  PORT=<端口>
set -u
cd "$(dirname "$0")/.."
ROOT="$PWD"
OUT="$ROOT/.runtime"
DST="$ROOT/bundle/screenshots"
mkdir -p "$DST"

# shellcheck source=tools/_env.sh
. "$ROOT/tools/_env.sh"

static_gate

echo "=== 启动宿主 ==="
boot_host "$OUT/run-shots.log"
assert_clean
echo "宿主就绪"

E2E_LOG="$OUT/run-shots-e2e.log"
: > "$E2E_LOG"
# ⚠️ 不要把输出丢掉（2026-09-30 修）：曾经因为 `e2e open` 在宿主刚 detach 返回时
#    扑空（按钮还没进布局树），整条导入链静默失败 —— 跑出来一张
#    「已加载 0 个事件」的空状态图，而每步输出都被 `>/dev/null` 吞了，毫无提示。
#    现在输出同时进终端与日志，并在收尾处检查有没有 FAIL。
e2e() { "$PY" tools/e2e.py "$@" 2>&1 | tee -a "$E2E_LOG"; }

# ── 截图 + 自检 ───────────────────────────────────────────────────────
LAST_MD5=""
SHOT_BAD=0
# 截图：加随机参数破缓存（代理/中间层会缓存同一 URL 的响应 → 拿到陈旧帧）
#
# ⚠️⚠️ 为什么每张都要跟上一张比 md5（2026-09-30 血泪）：
#   本脚本**真的踩到过** —— `03-conflict.png` / `04-conflict-detail.png` /
#   `05-after-advice.png` 三张的 md5 **完全一样**（同一帧、同为 155303 字节），
#   而脚本一声不吭地把它们当成了三张不同状态的商店截图。
#   它**不是「点击没生效」**：同一次运行的日志里，`more_btn` 的文案确实从
#   「详情」变成了「收起详情」、状态行也从「发现 1 处时间冲突」变成
#   「已应用 1 条改期建议 · 剩余 0 处冲突」；对照实验也证明「两个不同的状态」
#   之间能抓到不同的帧。所以是**那一轮抓到的帧是旧的**（界面已变、帧未跟上）。
#   偶发：紧接着重跑一次就恢复正常 —— 这才是它最危险的地方：**静默、不可复现、
#   直接进交付物**，而且原先「收尾查 FAIL」的机制完全拦不住（它连 FAIL 都没产生）。
#   ⇒ 唯一可靠的防线是**每抓一张就跟上一张比字节**，相同即判失败。
shot() {
  local f="$DST/$1" md5 size
  sleep 0.6
  $CURL "http://127.0.0.1:$PORT/g?raw=1&t=$RANDOM$RANDOM" -o "$f" 2>/dev/null
  md5=$(md5sum "$f" | cut -c1-16)
  size=$(stat -c%s "$f" 2>/dev/null || echo "?")
  echo "  shot $1  md5=$md5  ${size}B"
  if [ "$md5" = "$LAST_MD5" ]; then
    echo "  ★ FAIL: $1 与上一张截图**字节完全相同** —— 界面未变化，或抓到了陈旧帧。" >&2
    SHOT_BAD=1
  fi
  LAST_MD5="$md5"
}

# 状态断言：$1 = 说明，$2 = 应当出现在页面文本里的串
# 光有「截图互不相同」还不够 —— 两张不同的图也可能**都不对**。
expect_text() {
  local t; t=$("$PY" tools/e2e.py texts 2>&1)
  case "$t" in
    *"$2"*) echo "  OK   $1" ;;
    *) echo "  ★ FAIL $1 —— 期望页面出现「$2」，实际末尾：" >&2
       printf '%s\n' "$t" | tail -2 >&2
       SHOT_BAD=1 ;;
  esac
}

# 状态断言：$1 = 说明，$2 = **不应**出现的串
expect_absent() {
  local t; t=$("$PY" tools/e2e.py texts 2>&1)
  case "$t" in
    *"$2"*) echo "  ★ FAIL $1 —— 页面不该出现「$2」" >&2; SHOT_BAD=1 ;;
    *) echo "  OK   $1" ;;
  esac
}

# 状态断言（日志通道）：$1 = 说明，$2 = 应当出现在 E2E_LOG 里的串。
# ⚠️ 有些状态**不在页面文本里**，而在 TextInput 的 `entry` 中 —— 最典型的是「导出」：
#    ICS 正文是灌进输入框的，而 texts 只输出 Label / Button 的 `t` 字段，
#    不含输入框的值。所以对这类状态用 `e2e` 命令**自己的输出**断言（它已 tee 进日志）。
expect_log() {
  if grep -q "$2" "$E2E_LOG"; then
    echo "  OK   $1"
  else
    echo "  ★ FAIL $1 —— 日志里没出现「$2」" >&2
    SHOT_BAD=1
  fi
}

echo "=== 灌入 seed.ics ==="
e2e open; e2e fill seed.ics; e2e parse; e2e write

echo "=== 01 主界面（月历 + 事件列表）==="
# ⚠️⚠️ 断言必须放在**滚动之前**（2026-10-01 修）：
#    状态条在页面 y≈237。`scroll 260` 之后它落到屏幕外，而 `/snap` 只返回
#    **落在视口里**的控件 —— 于是这条断言永远找不到「已写入 3 个事件」。
#    它长期是红的却没人发现，因为收尾的 FAIL 匹配只认行首的 `FAIL`，
#    而这里失败时打的是 `  ★ FAIL …`（前面有缩进和一个 ★）——
#    **一条永远失败、又永远不被上报的断言**，比没有断言更危险。
#    现在：先断言（页面还在顶部），再滚动、再截图。
expect_text "seed 已写入（3 个事件）" "已写入 3 个事件"
# 往下滚一点，让月历和列表同框
e2e scroll 260
shot "01-list.png"

echo "=== 02 导入面板 ==="
e2e scroll -400
e2e open
expect_text "导入面板已打开" "解析"
shot "02-import.png"

echo "=== 03 冲突检出 ==="
e2e fill conflict.ics
e2e parse
e2e write
# ⚠️ 必须用**强断言**（「应出现 X」），不能用「不该出现 Y」：
#    `write` 是**分块**执行的（单 handler 200000 指令 / 64ms 双限），
#    若断言写成「不该出现『收起详情』」，那么在**冲突条还没建出来**时它同样成立
#    —— 断言过了，但页面其实是中间态。真正该断言的是「冲突已检出、详情未展开」。
expect_text "冲突已检出（1 处时间冲突）" "发现 1 处时间冲突"
expect_absent "详情未展开" "收起详情"
shot "03-conflict.png"

echo "=== 04 冲突详情 ==="
e2e more
expect_text "点「详情」后按钮变为「收起详情」" "收起详情"
shot "04-conflict-detail.png"

echo "=== 05 应用建议后 ==="
e2e advice
expect_text "建议已应用" "已应用"
shot "05-after-advice.png"

echo "=== 06 导出 ICS ==="
e2e open
e2e export
expect_log "导出到 entry 的 ICS 正文完整" "BEGIN:VCALENDAR"
shot "06-export.png"

echo "=== 07 关于页 ==="
e2e cancel
e2e about
expect_text "关于页已打开" "队伍 OMA"
shot "07-about.png"

echo "=== 08 点格子直接写日程（选中高亮 + 新建面板 + 每年重复）==="
# 关掉关于页 → 月历回来 → 点一格 → 写标题 → 重复切到「每年」。
# ★ 这一步同时是一条回归：**关于页开着时新建面板必须被收起**（三个面板互斥），
#   反过来「新建面板开着再点关于」也要能正常打开关于页 —— 后者正是下一步。
#
# ⚠️ 摆状态交给 python（要按**分区名 / 控件 id** 操作，bash 做不了），
#    但**退出码必须检查**：摆状态失败时界面往往还是「像那么回事」的，
#    图看着正常、内容却是错的 —— 这正是商店截图最危险的失败方式。
runpy() {  # $1 = tools/ 下的脚本名，其余是它的参数
  local rc
  "$PY" "tools/$1" "${@:2}" 2>&1 | tee -a "$E2E_LOG"
  rc=${PIPESTATUS[0]}
  if [ "$rc" != "0" ]; then
    echo "  ★ FAIL $1 $* 退出码 $rc —— 状态没摆对，这张图不可信" >&2
    SHOT_BAD=1
  fi
  return 0
}

e2e about
runpy shotnew.py
expect_text "新建面板已展开（写在这一天）" "写在这一天"
expect_absent "指标行已为面板让位" "来源"
shot "08-new-event.png"

# ── 09–12：2026-10-01 新增的四个分区 ──────────────────────────────────
# 为什么要新出这四张：这些分区是这个应用相当一部分体积所在（各自的存储、
# 各自的增删改），而 store listing 原来一张都没展示 —— 看截图完全看不出
# 「还有待办 / 心情 / 目标 / 小知识」。
#
# ⚠️ 截图仍由这里的 shot() 抓，不能绕过那道「相邻两张字节相同即判失败」的防线。
#
# ⚠️⚠️ 为什么点分区之前必须先关面板（2026-10-01 踩到，误诊过一次）：
#    `sync_panels()` 里有一行 `ui.tabbar.set_visible(!panel_on)` —— 新建 / 导入 /
#    关于**任一面板打开**时，分区导航条**整条收起**。这是刻意的：面板打开时的
#    竖向几何与「还没有导航条」时完全一致，从结构上排除「导航条把面板底部按钮
#    挤出 892px 视口」。
#    后果：第 08 步结束时新建面板还开着，此时 `e2e btn 待办` 报的是
#    **「找不到按钮『待办』」** —— 分区按钮不是没建出来，是**当前根本不该显示**。
#    第一次排错时我误判成「页面滚动导致导航条滚出视口」，写了一版反复滚轮
#    回顶的 `top()`，白白多跑了两轮四分钟的截图。
#    真正该做的是**先关掉面板**：`e2e cancel` 点新建面板的「取消」。
#    （不能靠「切到别的分区」来关它 —— 切分区要点的正是那个已经收起的按钮。）
close_panel() {
  e2e cancel
}

echo "=== 09 待办清单 ==="
close_panel
e2e btn 待办
runpy shotfeat.py todo
expect_text "待办分区已就绪（已完成 1 / 3）" "已完成 1 / 3"
shot "09-todo.png"

echo "=== 10 情绪日记 ==="
e2e btn 心情
runpy shotfeat.py mood
expect_text "心情已选（小结出现「心情：」）" "心情："
shot "10-mood.png"

echo "=== 11 目标与子任务 ==="
e2e btn 目标
runpy shotfeat.py goal
expect_text "目标进度条已到半格" "#####-----"
shot "11-goal.png"

echo "=== 12 小知识（今日 + 时间胶囊）==="
e2e btn 小知识
runpy shotfeat.py egg
# 断言「有收录」而不是「分区在」：这一步会往后走到第一个有内容的日子，
# 只查「解封日」的话，即使它还停在空状态也一样能过。
expect_text "小知识分区已就绪（时间胶囊在）" "解封日"
expect_absent "「今日」卡不是空状态（shotfeat 已走到有收录的日子）" "暂时没有收录"
shot "12-egg.png"

echo
echo "编译/运行错误数: $(host_error_count "$OUT/run-shots.log")"
kill_host

# ── 收尾检查（三道）─────────────────────────────────────────────────
# 1) 任一步 e2e 报 FAIL → 空状态图比报错更危险，因为它「看起来像一张正常截图」。
#    也覆盖 `  ★ FAIL …`（expect_text / expect_absent / shotfeat 的状态没摆对）。
# 2) 相邻两张截图字节完全相同 → 抓到了陈旧帧（见 shot() 上的说明）。
# 3) 状态断言（expect_text / expect_absent）失败 → 图不同，但状态不对。
#
# ⚠️ 匹配必须同时认「行首 FAIL」和「★ FAIL」（2026-10-01 修）：
#    原先只写 `^\s*FAIL|^FAIL`，于是 `  ★ FAIL …` **一个都匹配不到** ——
#    第 01 步的断言因此红了整轮都没被上报（见那一步的注释）。
RC=0
if grep -nE "★ FAIL|^FAIL" "$E2E_LOG"; then
  echo
  echo "FAIL: 截图流程里有失败的步骤，产物不可信（上面这些行）"
  RC=1
fi
if [ "$SHOT_BAD" != "0" ]; then
  echo
  echo "FAIL: 截图自身检查未通过（见上面的 ★ FAIL 行）。"
  RC=1
fi

echo
echo "=== 最终截图（md5 各不相同才算通过）==="
md5sum "$DST"/*.png
[ "$RC" = "0" ] && echo "SHOTS PASS" || echo "SHOTS FAIL"
exit "$RC"
