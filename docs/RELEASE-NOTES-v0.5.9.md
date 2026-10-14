# OctoSense 日历 v0.5.9 发布说明

日期：2026-10-14 · 基线：v0.5.8（tag `v0.5.8` → `a544150b`，被测 HEAD `189860e`）
主题：v0.5.8 双平台（Linux + Windows 11）测试报告修复 —— 版本号治理 + 测试链路根治

## 发布件

| 项 | 值 |
|---|---|
| Commit | `a9d8649a22ee2ab7d58cce539c583087a850b848`（分支 `v0.5.9`，自 main `189860e` 开出，已合入 main） |
| Tag | `v0.5.9` |
| Release | id `412322806`（已发布，非 draft） |
| Zip | `octosense-calendar-0.5.9-bundle.zip` · 2,764,749 bytes · sha256 `a3a8bef862a486c917851e81583f91067757174b45b13c1cb6fecea7dfe7f90b` |
| Bundle blake3 | `0106d913a6078da374df4920ad8b0c3876658c5c5ead68dfcc1cd8fdf0571adc` |
| Publisher key id | `OMA` |

## 一、应用侧改动

### 1. 关于页版本号漂移修复（Windows 报告 P1，本地已核实）

v0.5.8 关于页写死「版本 0.5.4 · Apache-2.0」而 manifest 已为 0.5.8，用户无法确认实际运行版本。修复：关于页改为 0.5.9，并**新增 `tools/version_gate.py` 静态门禁**——manifest.version 为唯一版本源，与关于页版本串漂移即红（静态门禁 13 → 14 道）。

### 2. geocoding 域：明确不删（反驳 Windows 报告 P3）

Windows 报告建议删除 `geocoding-api.open-meteo.com`，依据「日志 0 请求 + 源码 0 引用」——证据不成立：该域经宿主内建 `sys.geocodenum` 调用、仅在你点城市按钮时触发，URL 由宿主拼装（v0.5.1 曾误删过一次）。**两域保持不变**；listing.json 描述已补充触发路径说明。

### 3. Windows 天气 reserved-header（报告 P2）——toolchain 侧已修

报告实测「应用设 User-Agent 被宿主保留名单拒绝」。本地核实：toolchain 源码（`makepad/platform/src/script/res.rs`）已于 2026-10-13（v0.5.7 P0-1）移除自定义 User-Agent，应用源码无任何 header 设置；报告所用宿主 release 预编译二进制早于该修复。**请各测试机用当前 toolchain 重编 card-host 后复测天气**。

## 二、测试设施修复（随包 tools/ 更新）

### T1（P1）run_festival「班」字断言改快照文本（Linux 确定性失败根治）

v0.5.8 Linux 报告：llvmpipe 下字形位置偏移使 6 处「班」字像素判定确定性落空（期望 EVENT 实际 NONE，证据截图渲染正确）。修复：硬性断言改读 `.snap.json` 控件树文本（新增 `BAN_SNAP`，与字体渲染完全无关）；像素判色保留输出但降级为 WARN；`glyph_kind` 扫描矩形外扩 4px 并加「深色像素」降级，跨平台字形偏移不再判红。

### T2（P2）标记点断言改集合匹配

从「整行序列精确匹配」放宽为「颜色种类 + 个数」的集合匹配（多读到的 NONE 忽略），消除采样时序与翻页动画竞态造成的偶发红。

### T3（P1·工具侧）featflow 分区点击加判据 + 重试

Windows 平台合成点击到达率 ~90-95%，单次丢失曾使 run_features 20 项断言连坐失败。`click_label` 增加「点击后判据校验 + 重试（3 次）」，五个分区各配标志性控件判据；不改应用。

### T4（P3）可移植性

新增 `tools/mkdev_bundle.sh`（一键制作剥签名 dev bundle 副本）；`boot_host` 找不到宿主时的报错补充 `OCTO_BUNDLE` 用法提示。

## 三、验证状态

- 静态门禁 **14 道**全过（含新增 version_gate；13 道既有门禁无回归）。
- 定点复跑：`run_festival` PASS（新版「班」字/集合断言全过）、`run_features` PASS（featflow + restore + 布局扫描，宿主 `[E]` 0）。
- **全量回归 9/9 PASS**（2026-10-14 macOS 串行，9m36s）：`run_e2e` 10/10 · `run_conflict` 21/21（ICS 往返 0/0/N）· `run_edge` / `run_negative` / `run_festival` / `run_layout` / `run_new` / `run_features` / `run_new_features` 18/18 —— 应用/断言失败 **0** 条，前置/夹具失败 **0** 条，全程宿主 `[E]` **0**。
- `hub check` → **PASSED**（capabilities / hosts / storage 声明不变）。

## 四、不变式

- 不新增 capability / network.hosts（仍 2 个 Open-Meteo 域）；
- `reschedule()` 唯一写入点、七道闸判定、ICS 往返 0/0/N 全部保持；
- 应用本体零功能改动，本版为治理 + 测试链路版本。
