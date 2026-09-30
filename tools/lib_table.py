#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把一个「表格数据」渲染成资料库 Doc 的 <Table> 组件语法。

为什么单独抽出来：`submit_doc_edit.py` 的 schema 有三处硬约束，手写极容易踩，
  1. actions 文件必须是**裸数组** `[{...},{...}]`，不能包 `{"actions":[...]}`；
  2. 动作的**类型字段叫 `type`**（不是 `action`），定位字段叫 **`id`**（不是 `blockId`）；
     类型写错时报的是「actions[0] 的 type 无效或不允许」，完全指不到字段名；
  3. `<Mark>` 只支持 ar / backgroundcolor / bold / color / comment / italic /
     strike / underline —— **没有 `code`**，单元格里想写行内代码要先把反引号去掉。
本脚本只产出组件语法，别的什么都不做（不联网、不发请求）。

约定（组件语法约束，来自 skills/library/doc/table_edit_helper.py 的说明）：
  · TableCell 里的文字必须包一层 <Paragraph>
  · 表头行用 <Mark bold>…</Mark> 包裹
  · 4 空格缩进，不用 Tab
  · 子块之间不留空行
  · 不写 id / readonly

用法：
    python tools/lib_table.py                 # 打印全部 4 张表的组件语法
    python tools/lib_table.py --json out.json # 连同占位块 id 一起生成 actions 文件
"""
import argparse
import io
import json
import sys

# ── 四张表的内容（与 docs/holiday-and-festival-test.md 保持一致）──────────
T1 = {
    "head": ["当天性质", "日期文字", "标记", "颜色"],
    "rows": [
        ["法定放假", "绿色加粗 (c_ok)", "小绿点", "#15803d"],
        ["调休补班（本该休息的周末被调来上班）", "赤陶 (c_accent)", "一个「班」字", "#b4531f"],
        ["有节日但照常上班（如万圣节、妇女节）", "常规墨色 (c_ink2)", "深灰小黑点", "#6b6560"],
        ["有日程", "不变", "赤陶小点", "#b4531f"],
        ["普通日", "次级墨色", "无", "—"],
    ],
}
T2 = {
    "head": ["模式", "中国节假日数据", "国际固定节日", "放假标记"],
    "rows": [
        ["节日 中国", "显示", "不显示", "显示"],
        ["节日 国际", "不显示", "显示", "全部隐藏"],
        ["节日 全部", "显示", "显示", "显示"],
    ],
}
T3 = {
    "head": ["单元格高度", "标记行实得高度", "结果"],
    "rows": [
        ["34 px", "8~13 px", "「班」= 2 px 残片"],
        ["46 px", "17 px", "仍是残片"],
        ["52 px（最终）", "23 px", "「班」完整清晰"],
    ],
}
T4 = {
    "head": ["步骤", "状态", "期望", "结果"],
    "rows": [
        ["2", "2026-09 · 中国", "节日行「中秋」· 放假 3 天 · 9/20 上班", "通过"],
        ["", "", "像素：OK,OK,OK + 「班」= EVENT", "通过"],
        ["3", "2026-10 · 中国", "国庆 · 放假 7 天 · 10/10 上班", "通过"],
        ["", "", "像素：OK×7 + 「班」= EVENT", "通过"],
        ["4", "2026-10 · 仅国际", "万圣节 10/31 · 放假行整行让位 · 0 个「班」", "通过"],
        ["", "", "像素：只有一个 WORK（深灰小黑点）· 无「班」", "通过"],
        ["5", "2026-10 · 全部", "国庆 · 万圣节 · 放假 7 天", "通过"],
        ["", "", "像素：OK×7,WORK + 「班」= EVENT", "通过"],
        ["6", "切回中国", "按钮轮转一周无残留", "通过"],
        ["7", "2025-10 · 中国", "国庆中秋 · 放假 8 天 · 10/11 上班", "通过"],
        ["", "", "像素：OK×8 + 「班」= EVENT", "通过"],
        ["8", "2025-09 · 中国", "9/28 上班 · 无放假", "通过"],
        ["", "", "像素：一个点都没有 · 「班」= EVENT", "通过"],
        ["9", "错误检查", "宿主日志 [E] 数 = 0", "通过"],
    ],
}
TABLES = [T1, T2, T3, T4]


def esc(s):
    """组件语法里的转义；同时去掉行内代码反引号（<Mark> 不支持 code）。"""
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace("`", ""))


def cell(text, bold=False):
    body = esc(text)
    if bold:
        body = "<Mark bold>%s</Mark>" % body
    return ("            <TableCell>\n"
            "                <Paragraph>%s</Paragraph>\n"
            "            </TableCell>" % body)


def table_xml(t):
    out = ["<Table>"]
    out.append(("        <TableRow>\n"
                + "\n".join(cell(h, bold=True) for h in t["head"])
                + "\n        </TableRow>"))
    for r in t["rows"]:
        out.append(("        <TableRow>\n"
                    + "\n".join(cell(c) for c in r)
                    + "\n        </TableRow>"))
    out.append("</Table>")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", nargs=4, metavar=("ID1", "ID2", "ID3", "ID4"),
                    help="四个占位块（Paragraph）的 blockId，顺序对应 T1..T4")
    ap.add_argument("--out", help="把 actions 裸数组写到此文件")
    a = ap.parse_args()

    xmls = [table_xml(t) for t in TABLES]

    if not a.ids:
        for i, x in enumerate(xmls, 1):
            print("=" * 20, "TABLE_%d" % i, "=" * 20)
            print(x)
            print()
        return

    # insert_before：插到占位块之前；再 delete 占位块。
    # ⚠️ 三个硬约束（都踩过）：
    #   1. 动作的**类型字段叫 `type`**，不是 `action` —— 写错报
    #      「actions[0] 的 type 无效或不允许」，信息完全指不到字段名。
    #   2. 定位字段叫 `id`，不是 `blockId`。
    #   3. 文件必须是**裸数组** `[{...},{...}]`，不能包 `{"actions":[...]}`。
    actions = []
    for pid, xml in zip(a.ids, xmls):
        actions.append({"type": "insert_before", "id": pid, "content": xml})
    for pid in a.ids:
        actions.append({"type": "delete", "id": pid})
    text = json.dumps(actions, ensure_ascii=False, indent=2)
    if a.out:
        io.open(a.out, "w", encoding="utf-8").write(text)
        print("已写出 %s（%d 个动作）" % (a.out, len(actions)))
    else:
        print(text)


if __name__ == "__main__":
    sys.exit(main())
