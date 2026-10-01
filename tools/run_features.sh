#!/usr/bin/env bash
# OctoSense 端到端实测 · ⑧ 新功能分区（待办 / 心情 / 目标 / 彩蛋 / 视图 / 吉祥物 / 胶囊）
#
# 为什么单独立项：前七条流程覆盖的是「导入 → 冲突 → 往返 → 边界 → 节假日 → 布局 →
# 手工新建」，全部围绕**日程**。而 2026-10-01 新增的六个分区是全新的代码路径
# （各自的存储文件、各自的增删改、各自的静态槽位同步），一条断言都没有。
#
# 这条流程的存在意义，在写完它之前就已经兑现了一半：为了让 E 段「与源码数据表
# 交叉校验」能通过，才去把 `HISTORY` / `SOLAR_TERMS` 扒下来比对 —— 一比对就发现
# 两个「静静失败」的真 bug（日期键写成 "09-30" 而表里是 "0930"；
# `search` 返回**字节**下标而本项目 `substr` 按**字符**切）。两者都表现为
# 「界面有字、但字是错的」，只看截图永远发现不了。
#
# 六步：
#   [1] 起宿主（空库，含存储干净前置检查）
#   [2] featflow.py —— 六个分区的**语义**断言（与源码数据表交叉校验）
#   [3] 四个旁路 json 必须真的落盘（本地优先的磁盘证据）
#   [4] 换一个进程重启 → featflow.py --restore（本地优先的进程证据）
#   [5] featflow.py --scan —— 9 个新界面的**几何**扫描（⑥ run_layout 已扫过日程侧的 12 个）
#       ⚠️ 必须排在 [4] 之后：它会往待办/目标写数据，跑在前面会改掉 restore 的期望值
#   [6] 两个宿主的编译/运行错误数必须都是 0
#
# 用法: bash tools/run_features.sh
set -u
cd "$(dirname "$0")/.."
ROOT="$PWD"
OUT="$ROOT/.runtime"
EV="$OUT/evidence"
mkdir -p "$EV"

# shellcheck source=tools/_env.sh
. "$ROOT/tools/_env.sh"

static_gate

echo "=== [1/6] 启动宿主（空事件库）==="
boot_host "$OUT/run-features.log"
assert_clean
echo "宿主就绪  存储目录 $APP_DATA"

echo
echo "=== [2/6] 六个分区的交互断言 ==="
"$PY" "$ROOT/tools/featflow.py"
FF=$?
if [ "$FF" != "0" ]; then
  echo "  FAIL featflow.py 退出码 $FF"
else
  echo "  OK   featflow.py 全部通过"
fi

echo
echo "=== [3/6] 本地优先存储：四个旁路文件必须真的落盘 ==="
# 「离线可用、本地优先」是用户的硬要求，所以不能只断言界面——要断言**磁盘上真有文件**。
# 宿主把应用私有目录 jail 在 $APP_DATA/com.oma.octosense.calendar 下（见宿主日志
# 的 "isolate jailed at …" 一行）。featflow 写过待办/心情/目标/胶囊，四个文件都该在。
APPDIR="$APP_DATA/com.oma.octosense.calendar"
STOREOK=1
for f in todos.json moods.json goals.json capsules.json; do
  if [ -f "$APPDIR/$f" ]; then
    printf "  OK    %-14s %s 字节\n" "$f" "$(wc -c < "$APPDIR/$f" | tr -d ' ')"
  else
    printf "  MISS  %-14s 没落盘！\n" "$f"
    STOREOK=0
  fi
done

echo
echo "=== [4/6] 本地存储真的能读回（重启宿主，数据仍在）==="
# 这一步才是「本地优先」的硬证据：**换一个进程**再读一次。
# 同一个进程里读内存数组不算数 —— 那个从没坏过。
# ⚠️ 必须**复用**同一个 app-data 目录（boot_host 的第二个参数）：
#    默认行为是每轮换一个全新目录，那样重启后必然读到空库，
#    这条断言就会退化成「永远通过」的假测试。
kill_host
boot_host "$OUT/run-features2.log" "$APP_DATA"
"$PY" "$ROOT/tools/featflow.py" --restore
FF2=$?
if [ "$FF2" != "0" ]; then
  echo "  FAIL featflow.py --restore 退出码 $FF2"
else
  echo "  OK   重启后数据读回一致"
fi

echo
echo "=== [5/6] 新界面的几何扫描（零尺寸 / 负坐标 / 越界）==="
# ⚠️ 为什么必须排在 --restore **之后**：这一步会往待办/目标里写数据，
#    跑在前面会把 --restore 的期望值（心情=低落、目标=空）直接改掉。
#
# 为什么需要它：run_layout.sh 的 12 步覆盖的全是日程侧，
# 待办/心情/目标/彩蛋/日周视图**一步都没被几何检查过**，
# 而它们各自都有 on_render 动态容器 —— 正是最容易「被压成 0 高」的地方。
# 这类问题不报错（宿主日志 0 个 [E]），只有人站在那一页才看得出来。
"$PY" "$ROOT/tools/featflow.py" --scan
FF3=$?
if [ "$FF3" != "0" ]; then
  echo "  FAIL featflow.py --scan 退出码 $FF3"
else
  echo "  OK   9 个新界面状态均无几何异常（⑥ 已覆盖日程侧的 12 个，合计 21 个）"
fi

echo
echo "=== [6/6] 错误检查 ==="
NERR=$(host_error_count "$OUT/run-features.log")
NERR2=$(host_error_count "$OUT/run-features2.log")
echo "第一个宿主错误数: $NERR"
echo "第二个宿主错误数: $NERR2"
grep '\[E\]' "$OUT/run-features.log" 2>/dev/null | head -5 || true
grep '\[E\]' "$OUT/run-features2.log" 2>/dev/null | head -5 || true
echo "证据文件:"
ls "$EV" | grep '^ft-' || true

kill_host

if [ "$FF" != "0" ] || [ "${FF2:-1}" != "0" ] || [ "${FF3:-1}" != "0" ] \
   || [ "$STOREOK" != "1" ] || [ "$NERR" != "0" ] || [ "$NERR2" != "0" ]; then
  echo "结论：FAIL"
  exit 1
fi
echo "结论：PASS"
exit 0
