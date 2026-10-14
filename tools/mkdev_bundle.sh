#!/usr/bin/env bash
# 一键制作「剥签名 dev bundle」副本（v0.5.9 T4）。
#
# 背景：release bundle 带 OMA 签名（integrity.signature），本机 card-host
# 内置 RefuseAllSignatures 会直接拒签，报出来的却是「FATAL: 应用存储不干净」
# 这种与真因无关的错。任何本地测试都要先做剥签名副本（v0.5.8 Linux 报告 P3：
# 此前每个测试环境各写一份，收敛成这一个脚本）。
#
# 用法：
#   bash tools/mkdev_bundle.sh                 # bundle → .runtime/bundle-dev
#   bash tools/mkdev_bundle.sh <src> <dst>     # 自定义源/目标
# 跑测试：
#   OCTO_BUNDLE=.runtime/bundle-dev bash tools/run_all.sh
set -u
cd "$(dirname "$0")/.."
SRC="${1:-bundle}"
DST="${2:-.runtime/bundle-dev}"

if [ ! -f "$SRC/manifest.json" ]; then
  echo "FATAL: $SRC 里没有 manifest.json（源目录不对？）" >&2
  exit 2
fi

rm -rf "$DST"
mkdir -p "$DST"
cp -R "$SRC/." "$DST/"

# 只剥 signature：bundle_blake3 是完整性戳，保留让宿主继续校验文件完整性。
PYBIN="${PY:-python3}"
"$PYBIN" - "$DST/manifest.json" <<'EOF'
import json, sys
p = sys.argv[1]
m = json.load(open(p, encoding="utf-8"))
sig = m.get("integrity", {}).pop("signature", None)
json.dump(m, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2, sort_keys=True)
open(p, "a", encoding="utf-8").write("\n")
print("  剥除 integrity.signature：%s" % ("已剥" if sig else "原本就没有"))
EOF

echo "dev bundle 就绪：${DST}（用 OCTO_BUNDLE=${DST} bash tools/run_all.sh 跑测试）"
