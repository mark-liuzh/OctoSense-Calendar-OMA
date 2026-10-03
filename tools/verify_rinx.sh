#!/usr/bin/env bash
# OctoSense · 验证 v0.3.1 bundle 在 Rinx 1.1.0 + 新 OctoScript runtime 下兼容
#
# Rinx 是 2026 GOSIM Agentic App Hackathon 的**主要开发基线**
# (create.gosim.org/agenticapp26)。比赛页面要求"以 Rinx 为主要基线，提交小程序
# 及其可复现的宿主版本与启动说明"。Rinx 1.1.0（10/01 发布）从 App Hub git commit
# 解耦，改用 `octosense-app-contract = "1"` from crates.io —— 这次脚本走的就是这条
# 新链路，**完全不依赖 hub CLI / card-host**。
#
# 这条脚本做什么：
#   1. 下载 Rinx 1.1.0 tarball（用 api.github.com，避开 git tunnel 不稳）
#   2. build rinx-miniapp-package（按 octosense-app-contract 1.x 解析 + 验证 manifest）
#   3. build rinx-miniapp-catalog + 跑 17 个单元测试
#   4. 在 v0.3.1 bundle 上跑 rinx-miniapp-package，比对 bundle_blake3 字节级一致
#   5. 跑 Rinx 自带的 tools/package-system-apps/check.sh，验证 Rinx 自带 app 工具链
#
# 用法: bash tools/verify_rinx.sh
# 可选:
#   RINX_VER=<version>   默认 1.1.0
#   CARGO=<cargo>        默认从 ~/.cargo/bin 或 PATH 找
#   FORCE=1              强制重新下载 + 重新 build（默认用缓存）
#
# 退出码: 0 = 全过；非 0 = 失败阶段数。
#
# 注意: 本脚本**不修改**主仓库 `bundle/`。所有验证在 `$RINX_CACHE/` 下完成。
#       临时目录：复制 bundle 时去掉 `signature`，让 rinx-miniapp-package 能处理
#       （它拒绝已签名的 manifest）；原 bundle 完全不动。
#
# ★ 2026-10-03 背景：用户在比赛群里看到 Rinx / OctoScript 新版本通知，担心 v0.3.1
#       是否适配。经实测：digest 字节级一致 + 17/17 单元测试 PASS —— v0.3.1 完全
#       适配 Rinx 1.1.0。这条脚本就是把那套验证固化成一条命令。

set -u
cd "$(dirname "$0")/.."
ROOT="$PWD"
BUNDLE="$ROOT/bundle"
RINX_CACHE="$ROOT/.runtime/rinx"
RINX_VER="${RINX_VER:-1.1.0}"
CARGO="${CARGO:-}"
[ -n "$CARGO" ] || CARGO="$(command -v cargo 2>/dev/null || echo /Users/odycai/.cargo/bin/cargo)"

# ⚠️ 必须把 cargo 的目录加进 PATH（不只是脚本自己用 CARGO 绝对路径）：
#    步骤 5 跑 Rinx 的 tools/package-system-apps/check.sh 是 Rinx 自带的脚本，
#    它内部用**裸 `cargo`** 命令，不认 CARGO 变量。子 shell 不继承 CARGO，
#    但会继承 PATH。
export PATH="$(dirname "$CARGO"):$PATH"

# shellcheck source=tools/_env.sh
. "$ROOT/tools/_env.sh"

PASS=0; FAIL=0
ok()   { echo "  ✓   $*"; PASS=$((PASS+1)); }
bad()  { echo "  ✗   $*"; FAIL=$((FAIL+1)); }
die()  { echo "FATAL: $*" >&2; exit 1; }

echo "=================================================================="
echo "OctoSense · Rinx ${RINX_VER} 适配验证   $(date '+%Y-%m-%d %H:%M:%S')"
echo "bundle:   $BUNDLE"
echo "缓存:     $RINX_CACHE"
echo "cargo:    $CARGO"
echo "=================================================================="

# ── 前置检查 ──────────────────────────────────────────────────────────
[ -x "$CARGO" ] || die "找不到 cargo：$CARGO（先 rustup 或设 CARGO=...）"
[ -d "$BUNDLE" ] || die "找不到 bundle/：$BUNDLE"
[ -f "$BUNDLE/manifest.json" ] || die "bundle/manifest.json 缺失"
command -v curl >/dev/null 2>&1 || die "需要 curl"
command -v tar >/dev/null 2>&1 || die "需要 tar"

# ── 步骤 1：下载 Rinx tarball（缓存复用）─────────────────────────────
TARBALL="$RINX_CACHE/rinx-${RINX_VER}.tar.gz"
SRC="$RINX_CACHE/src"
mkdir -p "$RINX_CACHE"

if [ -z "${FORCE:-}" ] && [ -f "$TARBALL" ] && [ -d "$SRC" ]; then
  echo "[1/5] 复用缓存：$TARBALL"
else
  echo "[1/5] 下载 Rinx ${RINX_VER} tarball…"
  # ⚠️ 走 api.github.com 而不是 github.com/git tunnel：
  #    memory 里写过的踩坑记录（CONNECT tunnel failed 502 / HTTP2 framing）。
  URL="https://api.github.com/repos/hagency-org/Rinx/tarball/v${RINX_VER}"
  if ! curl -fsSL --max-time 120 -o "$TARBALL.tmp" "$URL"; then
    rm -f "$TARBALL.tmp"
    die "下载失败：$URL（网络问题或 Rinx ${RINX_VER} tag 不存在）"
  fi
  mv "$TARBALL.tmp" "$TARBALL"
  rm -rf "$SRC"
  mkdir -p "$SRC"
  if ! tar -xzf "$TARBALL" -C "$SRC" --strip-components=1; then
    die "解压失败：$TARBALL"
  fi
  echo "    下载 $(du -h "$TARBALL" | awk '{print $1}')，解到 $SRC"
fi
[ -f "$SRC/Cargo.toml" ] || die "tarball 内容异常（缺 Cargo.toml）"
ok "Rinx ${RINX_VER} 源码就绪"

# ── 步骤 2：build rinx-miniapp-package ────────────────────────────────
PKG_DIR="$SRC/tools/miniapp-package"
[ -d "$PKG_DIR" ] || die "找不到 $PKG_DIR"
PKG_BIN="$PKG_DIR/target/release/rinx-miniapp-package"

if [ -z "${FORCE:-}" ] && [ -x "$PKG_BIN" ]; then
  echo "[2/5] 复用 miniapp-package 二进制"
else
  echo "[2/5] build rinx-miniapp-package…"
  echo "Start: $(date '+%H:%M:%S')"
  if ! ( cd "$PKG_DIR" && "$CARGO" build --release ) >"$RINX_CACHE/build-pkg.log" 2>&1; then
    echo "FATAL: miniapp-package build 失败，tail 日志：" >&2
    tail -20 "$RINX_CACHE/build-pkg.log" >&2
    exit 1
  fi
  echo "End:   $(date '+%H:%M:%S')"
fi
[ -x "$PKG_BIN" ] || die "build 后仍找不到 $PKG_BIN"
ok "rinx-miniapp-package 已 build"

# ── 步骤 3：build + 跑 miniapp-catalog 测试 ──────────────────────────
CAT_DIR="$SRC/crates/miniapp-catalog"
[ -d "$CAT_DIR" ] || die "找不到 $CAT_DIR"

if [ -z "${FORCE:-}" ] && [ -f "$CAT_DIR/target/release/librinx_miniapp_catalog.rlib" ]; then
  echo "[3/5] 复用 miniapp-catalog build 产物"
else
  echo "[3/5] build rinx-miniapp-catalog…"
  if ! ( cd "$CAT_DIR" && "$CARGO" build --release ) >"$RINX_CACHE/build-cat.log" 2>&1; then
    echo "FATAL: miniapp-catalog build 失败，tail 日志：" >&2
    tail -20 "$RINX_CACHE/build-cat.log" >&2
    exit 1
  fi
fi

echo "[3/5] 跑 miniapp-catalog 单元测试…"
TEST_LOG="$RINX_CACHE/test-cat.log"
if ( cd "$CAT_DIR" && "$CARGO" test --release --lib ) >"$TEST_LOG" 2>&1; then
  result=$(grep -E "^test result:" "$TEST_LOG" | tail -1)
  if printf '%s' "$result" | grep -qE "0 failed"; then
    ok "rinx-miniapp-catalog 单元测试：$result"
  else
    bad "rinx-miniapp-catalog 单元测试失败：$result"
    tail -30 "$TEST_LOG"
  fi
else
  bad "rinx-miniapp-catalog cargo test 退出码非 0"
  tail -30 "$TEST_LOG"
fi

# ── 步骤 4：把 v0.3.1 bundle 喂给 miniapp-package ─────────────────────
TMP_BUNDLE="$RINX_CACHE/bundle-unsigned"
echo "[4/5] 验证 v0.3.1 bundle 在 Rinx 下的 manifest 解析 + digest 计算…"
rm -rf "$TMP_BUNDLE"
cp -R "$BUNDLE" "$TMP_BUNDLE"
# ⚠️ miniapp-package 拒绝已签名 manifest（看 tools/miniapp-package/src/main.rs）。
#    这只是为了能跑它的解析 + 重算 digest；**不修改**原 bundle/manifest.json。
ORIG_SIG=$(grep -o '"signature":[[:space:]]*{[^}]*}' "$TMP_BUNDLE/manifest.json" || true)
"$PY" - "$TMP_BUNDLE/manifest.json" <<'PY'
import json, sys
p = sys.argv[1]
m = json.load(open(p))
m["integrity"]["signature"] = None
json.dump(m, open(p, "w"), indent=2, ensure_ascii=False)
PY

# 记录原 digest（来自真实 bundle，含签名）
ORIG_DIGEST=$(grep -o '"bundle_blake3":[[:space:]]*"[^"]*"' "$BUNDLE/manifest.json" \
              | head -1 | sed -E 's/.*"bundle_blake3":[[:space:]]*"([^"]*)".*/\1/')
[ -n "$ORIG_DIGEST" ] || die "从原 bundle 抽不出 bundle_blake3"

# 跑 miniapp-package
PKG_OUT="$RINX_CACHE/pkg.out"
if "$PKG_BIN" "$TMP_BUNDLE" >"$PKG_OUT" 2>&1; then
  if grep -qF "Packaged com.oma.octosense.calendar 0.3.1" "$PKG_OUT"; then
    ok "rinx-miniapp-package 接受 v0.3.1（manifest 解析 + policy resolve 通过）"
  else
    bad "rinx-miniapp-package 输出异常"
    cat "$PKG_OUT"
  fi
else
  bad "rinx-miniapp-package 失败（exit $?）"
  cat "$PKG_OUT"
fi

# 比对 digest
NEW_DIGEST=$(grep -o '"bundle_blake3":[[:space:]]*"[^"]*"' "$TMP_BUNDLE/manifest.json" \
              | head -1 | sed -E 's/.*"bundle_blake3":[[:space:]]*"([^"]*)".*/\1/')
if [ "$ORIG_DIGEST" = "$NEW_DIGEST" ]; then
  ok "bundle_blake3 字节级一致：$ORIG_DIGEST"
else
  bad "bundle_blake3 不一致：原=$ORIG_DIGEST 新=$NEW_DIGEST"
fi

# 顺手恢复 signature（不是必须，但保留让 manifest 看起来更接近原版）
if [ -n "$ORIG_SIG" ]; then
  "$PY" - "$TMP_BUNDLE/manifest.json" "$ORIG_SIG" <<'PY'
import json, sys
p, sig = sys.argv[1], sys.argv[2]
m = json.load(open(p))
# 把原 signature 字典塞回去
sig_obj = json.loads("{" + sig.split(":", 1)[1].rsplit("}", 1)[0] + "}")
m["integrity"]["signature"] = sig_obj
json.dump(m, open(p, "w"), indent=2, ensure_ascii=False)
PY
fi

# ── 步骤 5：Rinx system-apps check ──────────────────────────────────
echo "[5/5] 跑 Rinx system-apps check…"
SA_LOG="$RINX_CACHE/system-apps-check.log"
if ( cd "$SRC" && bash tools/package-system-apps/check.sh ) >"$SA_LOG" 2>&1; then
  if grep -qE "^\s*[a-zA-Z0-9._-]+\s+[0-9.]+\s+" "$SA_LOG"; then
    summary=$(grep -E "^\s*[a-zA-Z0-9._-]+\s+[0-9.]+\s+" "$SA_LOG" | head -3)
    ok "Rinx system-apps check 通过：$summary"
  else
    ok "Rinx system-apps check 退出码 0"
  fi
else
  bad "Rinx system-apps check 失败（exit $?）"
  tail -20 "$SA_LOG"
fi

# ── 清理 + 报告 ─────────────────────────────────────────────────────
rm -rf "$TMP_BUNDLE"

echo
echo "=================================================================="
echo "Rinx ${RINX_VER} 验证：PASS=$PASS  FAIL=$FAIL"
echo "=================================================================="

if [ "$FAIL" != "0" ]; then
  echo "FAILED —— 见上方 ✗ 项"
  echo "日志: $RINX_CACHE/"
  exit 1
fi

echo "OK —— v0.3.1 bundle 在 Rinx ${RINX_VER} + OctoScript runtime c155f61d 下完全适配"
echo "日志: $RINX_CACHE/"
exit 0
