# Developing this OctoSense app

> **Any coding agent, or none.** These instructions work the same for Codex, Claude Code, Cursor, Gemini CLI, GitHub Copilot or a person at a terminal: every step is a shell command or a file edit, and nothing here needs a particular agent, model or vendor. `AGENTS.md` is the one source of truth; `CLAUDE.md` and `GEMINI.md` only import it for agents that look for those names.

This repository is one OctoSense script app. `bundle/` is the app and the only
thing submitted to the App Hub; everything else stays outside it.

Follow the harness, and do not invent requirements or APIs:

- How to build, run and test: [QUICKSTART](https://github.com/OctoSense-org/OctoScript-App-Design-Flow/blob/main/docs/QUICKSTART.md)
- The language and every API an app may use: [SCRIPT-API](https://github.com/OctoSense-org/OctoScript-App-Design-Flow/blob/main/docs/SCRIPT-API.md)
- Capabilities: [CAPABILITIES](https://github.com/OctoSense-org/OctoScript-App-Design-Flow/blob/main/docs/CAPABILITIES.md)
- Publishing, step by step, with the human checkpoints: [PUBLISHING](https://github.com/OctoSense-org/OctoScript-App-Design-Flow/blob/main/docs/PUBLISHING.md)

The loop, with `OCTO=<path to OctoScript-App-Design-Flow>/tools/octo` (the CLI
lives in the harness repository, not here), run from this directory: edit
`bundle/main.splash` → `$OCTO run bundle --port 8141 --detach` → drive it
(`/click`, `/t`, `/snap`) and `$OCTO shot 8141 out.png` → `curl -s 127.0.0.1:8141/quit`
→ `$OCTO check bundle`.

Rules:

- Ask only for capabilities a screen uses; declare every `https://` host in
  `network.hosts`; never `http://`.
- Never collect a password, PIN or code; accounts go through a host service.
- Screenshots are real captures you looked at. Never a dummy.
- Restamp after every edit (`tools/octo check` does it). After signing, any
  edit needs a new stamp and signature.
- Keys, `.local-state/`, `build/` and review packets never enter `bundle/` or git.
- Stop at human steps: publisher key, publisher details, platform claims, submission.

Add this app's own requirements, data sources and tests below.

---

## 本应用（OctoSense 日历）的补充约定

### 它是什么

一个 ICS（iCalendar）交换工具：**粘贴导入 → 检出冲突 → 按承诺权重给改期建议 → 无损导出**。
界面严格照 `ui-design-v1.html` 复刻（设计语言：档案卷宗 —— 暖白纸底 `#faf9f7`、
暖黑墨色 `#191714`、单一赤陶强调色 `#b4531f`）。改动界面前先读那份设计稿，不要自行发挥。

### 权限：`storage` + `net`（仅 Open-Meteo 天气）+ `model`（v0.5.0 起）

`storage` 性质可写：事件库上限 16 MiB（宿主默认）。
`net` 性质**仅限天气**：月历每个格子的左上角读 Open-Meteo 公开预报，含过去 30 天的历史，
冷启动只拉一次并缓存到本机，离线回落到上次缓存；manifest 里
`network.hosts` **只列 `api.open-meteo.com` 一个域** ——
`geocoding-api` 与 `archive-api` 实测在代码里零引用（天气走 `sys.weather` 的逐日 pluck），
按「只申请界面用得到的权限」已移除（v0.5.0，依初赛评委建议 3）。
**禁止**任何其它网络调用、CDN 素材或遥测——评价、选图都会引向失败。素材一律打进
`bundle/`，宿主不会远程加载。

### 数据来源与写入方式

- 输入**只有一条路**：用户在导入框里粘贴的 ICS 文本。
  宿主没有文件选择器，`clipboard` 权限也无可用路径——不要尝试加「选择文件」按钮。
- 事件库存在宿主分配的私有存储中，上限 16 MiB。

### 硬性功能要求（改动后必须仍然成立）

1. **ICS 往返无损**：导出后原样再解析一次，必须报告「新增 0 / 改期 0 / 跳过 N」。
   导出时按事件类型补回 `;TZID=` / `;VALUE=DATE`；改期重建事件时按 `start_utc` 补回 `Z`。
2. **全天事件不参与自动改期**（`VALUE=DATE`）。
3. **冲突结论要分期**：重叠必须给出**时长**，而不是只说「有冲突」。
4. **有快照就要留回滚入口**：冲突归零后「回滚」按钮不能消失。
5. **改期只有一个写入点**：`reschedule(uid, day, slot_start, slot_end)`。
   规则引擎（`apply_advice`）与模型（`apply_model_plan`）**必须共用它**。
   两处各写一遍 `events[k] = {...}` 迟早漂移 —— 某天修了 `start_utc` 的 `Z` 后缀
   只改一处，第 1 条立刻回归。
6. **模型只写它被允许写的字段**：`ai_verify()` 的七道闸任一不过就当场退回规则建议。
   schema 只保证「形状」，保证不了「这个时段真的空着」，所以校验必须自己写一遍。

### 测试方式

```bash
bash tools/run_e2e.sh        # ① 基本流程
bash tools/run_conflict.sh   # ② 冲突 / 导出 / 往返 / 回滚 / 关于页
```

两者都会起真实宿主、用远程控制桥逐步操作，并在最后报告宿主日志里的
编译/运行错误数——**必须是 0**。改了 `main.splash` 就重跑，别只看截图。

⚠️ **本机跑回归必须显式给两个变量**（否则脚本起不来或打错进程）：

```bash
OCTO_CARD_HOST="$PWD/_toolchain/OctoSense-App-Hub/target/release/card-host" \
  bash tools/run_conflict.sh
# 跑开发副本（剥签名的 .runtime/bundle-*）时再加 OCTO_BUNDLE=.runtime/bundle-xxx
```

- `_env.sh` 的宿主搜索路径是 `$ROOT/../OctoSense-App-Hub/…`，而本机实际在
  `$ROOT/_toolchain/…` ⇒ 不给 `OCTO_CARD_HOST` 就 `HOST: unbound variable`。
- **每轮前 `pkill -9 -f card-host` 并换一个没用过的端口。** `boot_host` 的
  `port_busy` 检查只看「端口通不通」，手动起过的残留宿主会让整轮测试
  打在一个旧进程上，表现为**十几条莫名其妙的红**（事件数对不上之类）。
- **`bundle/` 是已签名的发布件，`card-host` 内置 `RefuseAllSignatures` 会直接拒签**，
  报出来的却是 `FATAL: 应用存储不干净`（与真因毫无关系）。
  跑任何本地验证都要先做一份**剥掉 `integrity.signature` 的副本**。

改完先跑静态自检（不启动宿主，秒级）：

```bash
python3 tools/brace.py  bundle/main.splash   # 括号是否平衡
python3 tools/quotes.py bundle/main.splash   # 引号是否成对
python3 tools/deps.py   bundle/main.splash   # 有无前向引用（Splash 不允许）
python3 tools/fncalls.py bundle/main.splash # 有无「调用了但从未定义」的函数名
```

### 已知的宿主坑（血泪，改布局前必读）

- **容器一律 `height: Fit`**。给容器写死像素高度会让内部 `Label` 被压缩、把文字裁掉，
  且改大也没用（裁切位置不动）。`Label` 一律不写 `height`。
- **`Label` 没有 `render()` 方法**（只有 `RoundedView` 等容器有）。
  在事件回调里写 `ui.some_label.render()` 会报
  `widget method render not found`（`widgets/src/widget_async.rs:1456`），
  **并且会静默中断该回调后面的所有语句** —— 曾因此让 `start_timeout` 压根没执行、
  界面永久停在「请求中」。动态 `Label` 的内容统一交给 `sync_*` 这类「`set_text` 刷一遍」
  的函数去刷。⇒ **回调里没生效时，先查宿主日志有没有 `[E] splash`。**
- **Splash 不支持三元表达式 `?:`**。`cond ? a : b` 会被解析器误识别为「named arg」，
  报 `Expected )` / `Expected } not found`（`script/src/parser.rs:3029`/`3392`）。
  ⚠️ `tools/brace.py` 与 `quotes.py` **抓不到**（括号确实配平），只有真跑宿主才炸。
  一律写成 `if/else` 先算出变量再用。改前先 `grep "? "`.
- **`set_visible(false)` 不解除父容器的占位**。父容器也要 `Fit`，否则隐藏面板仍占几十像素。
- **面板显隐要互斥让位**。任何让某条「常驻」的改动，都可能把按钮挤出 892 px 视口——
  改完必须跑上面两条 e2e 看回归。
- **`on_render` 里动态创建的按钮点击无效**（重建后不重绑）。需要点击的按钮必须静态声明，
  用 `set_visible` / `set_text` 控制。
- **宿主字体比浏览器宽约 40%**（`font_code` ≈0.8 em、`font_regular` ≈0.9 em，浏览器约 0.5 em），
  且每个 `Label` 另有约 7 px 水平开销。含中文处必须用 `font_regular`（`font_code` 无 CJK 字形，
  会显示成豆腐块）。
- **本地调试先查代理**：`env | grep -i proxy`。`http_proxy` 会把发往 `127.0.0.1` 的请求也劫持，
  返回 502 或上一帧的旧截图，症状极具误导性。

### 提交纪律

`bundle/` 是唯一提交内容；`tools/`、`docs/`、测试数据留在仓库里但不进 bundle。
改完 `bundle/` 后重跑 `octo check`（它会重新 stamp 完整性戳），别手工改 `manifest.json` 的
`integrity` 字段。

