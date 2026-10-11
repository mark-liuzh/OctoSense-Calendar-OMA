# 回归记录 · 2026-10-11（v0.5.2）

时间：2026-10-11 15:38–15:47 · 分支 `v0.5.2-dev` · 基线 v0.5.1（`12a36b8`）

## 怎么跑的

```sh
OCTO_CARD_HOST="$PWD/_toolchain/OctoSense-App-Hub/target/release/card-host" \
OCTO_BUNDLE=.runtime/bundle-dev \
PORT=8938 \
bash tools/run_all.sh
```

`OCTO_BUNDLE` 指向剥掉 `integrity.signature` 的副本 —— 本机 card-host 内置
`RefuseAllSignatures`，对任何带签名的 manifest 一律拒绝，而 OMA 公钥只在提交
App Hub 那侧安装。**这是本地验证的必要前置，不是绕过校验。**

## 结果

```
汇总：通过 8 / 8
应用/断言失败（结论有效）: 0 条
前置/夹具失败（脚本缺陷，不作应用结论）: 0 条
```

| 流程 | 断言 | 编译/运行错误数 |
| --- | --- | --- |
| `run_e2e` | 10 | 0 |
| `run_conflict` | 21（含「重叠 30 分钟」量化冲突、往返 0/0/N） | 0 |
| `run_edge` | 27（字段级往返无损，14 条硬断言） | 0 |
| `run_negative` | 8 | 0 |
| `run_festival` | 58（含像素级颜色判定） | 0 |
| `run_layout` | 12 个界面状态几何异常 0 | 0 |
| `run_new` | 31（点格子写日程 / 重复规则 / 往返，含 `rrule_guard`） | 0 |
| `run_features` | 6 个非日程分区 + 4 个旁路文件落盘 + 9 个新界面几何扫描 | 0 |

定点验收 `tools/verify_extra.sh`（W3-1 新增）：

```
提示行宽 360px / 可用 372px（安全线 364px）  OK
字段丢失数: 0（20 项逐字段比对，含 VALARM 容器的 BEGIN/END 成对往返）
往返结果: 新增 0 / 改期 0 / 跳过 2            OK
编译/运行错误数: 0
结论：PASS
```

静态门禁 13 道全过：`brace` / `quotes` / `toplevel` / `deps` / `paintfix` /
`btnfocus` / `cellhover` / `fncalls` / `ai_gates` / `host_errors` / `portability` /
`shellsafe` / `writepoint`。

## 本轮修掉的两个真回归（都是全量回归抓出来的，不是静态门禁）

### 1. 存量数据缺 `extra` 字段 → `run_conflict` 9 条红

W3-1 给事件加了 `extra` / `extra_kinds`，但用户本机已有的 `events.json` 是旧版本
写的、根本没有这两个键。Splash 读一个从没写过的键会抛
`property extra not found in prototype chain`，而**抛错之后该实例的后续写操作
全部静默失效** ⇒ 一个旧事件就让整条导出链路哑掉。

症状极具误导性：界面完全正常、`run_e2e` 也全过，只有 `run_conflict` 的
「导出 → 往返 → 回滚」这一段塌了，而报错指向的是「导出没内容」，
与真因（字段缺失）隔了三层。

修法：`load()` 读回后用 `with_extra()` 整体重建每个事件对象补齐字段。
**不能用「先探测再补」** —— 探测本身就会抛，抛完该实例就废了。

顺带发现第二处同类漏项：`reschedule()` 重建对象时也没带 `extra` ⇒
改期一次，那条事件的提醒/分类/参会人就永久没了。已补，并给 `writepoint.py`
加了第 ④ 条断言（字段表必须处处列全），反验确认它能抓到这两个错。

### 2. 导入面板提示行超宽 389px（可用 372px）

第一版文案用属性名原文（「…（CATEGORIES、CLASS、TRANSP 等），已原样保留」），
实测 `import_hint r=[23,273,389,24]`。Label 是 `width: Fill`，**溢出不会换行、
只会裁掉尾巴** —— 被裁掉的恰恰是「已原样保留」这句最该让用户看到的话。

改用中文短名（「分类、公开度、占用」）后 360px。顺带说，中文短名对用户也更有用。

## 复跑提醒

每轮前 `pkill -9 -f card-host` 并换端口。残留宿主会让整轮打在一个旧进程上，
表现为十几条莫名其妙的红。W1 之后这类红会被正确归类成「前置/夹具失败」，
不再与应用失败混在一起。
