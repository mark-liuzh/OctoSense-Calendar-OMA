# OctoSense 日历 v0.5.1

**2026 GOSIM Agentic App Hackathon · 队伍 OMA**（成员 `mark-liuzh`、`ody-cai`）

> v0.5.0 的核心是「模型参与改期，但决定权不在模型手里」。
> v0.5.1 做两件事：**把初赛评委四条建议的收口做干净**（A 类文档矛盾 4 条全修），
> 以及**正面答复评委建议 4** —— 天气不再写死北京，改成可以选城市。

---

## 一、评委建议 4 的正面答复：天气可按城市取

评委原话：「天气坐标硬编码北京，至少在右上角标记。」

v0.5.0 的处置是**加标注**（界面写明「天气按北京」）。v0.5.1 往前走一步：
**真的可以换城市了** —— 月历顶栏的城市按钮点开，输入城市名，应用换成经纬度后按该坐标取天气。

### 为什么仍然是「选城市」而不是「自动定位」

这是宿主能力决定的，不是偷懒：

- 应用跑在 OctoSense 隔离宿主里，脚本能读到的定位接口是 `sys.gps`；
- 按**宿主自己的源码注释**（`splash.rs` 的 `sys.gps` 实现）：
  > Fed by the **Android** LocationListener through JNI onLocation -> makepad_platform::gps.
- 也就是说 `sys.gps` 在设计上的唯一数据源就是 Android，
  **macOS / Windows 上没有 provider** ⇒ 恒定返回 `-9999`；
- 在桌面端申请 `location` 权限，只会让商店弹一句「使用你的位置」，
  却永远拿不到数据 —— 隐私上是净亏。

所以应用选了另一条路：**你说了哪个城市，就查哪个城市**。
默认仍是北京，顶栏按钮显示当前城市名，不装作是自动定位。
`manifest.json` 里**没有** `location` capability。

这个取舍在官方文档里也有依据 —— `octoscript/docs/ui-profile-l0.md` 写着：

> "Start from where I am" is not a fact the model may write — §4 forbids it,
> and rightly: **a coordinate a card carries is a place the device is not.**

卡片自带一个坐标并不是「设备在哪」。如实标注、再让用户自己选，才是诚实的做法。

### 怎么用

月历顶栏那个显示城市名的按钮 → 输入城市名 → 点「应用」。
换完立刻生效并记住选择（存在本机 `wx_city.json`）。

### 隐私口径随之变化

`network.hosts` 从 1 个域变成 **2 个**：

| 域 | 用途 | 什么时候发 |
| --- | --- | --- |
| `api.open-meteo.com` | 取天气 | 冷启动一次 |
| `geocoding-api.open-meteo.com` | 城市名 → 经纬度 | **只有你点「应用」时** |

发出的是「你输入的城市名」（例如「深圳」），**不含任何日程数据**。
第三个域 `archive-api.open-meteo.com` 早先声明了但代码实测零引用，v0.5.0 起不再声明。

---

## 二、A 类 · 文档与实现矛盾（4 条，本轮全修）

这 4 条的性质是**同一份提交里同时给出互相矛盾的答案** ——
`bundle/listing.json` 的 `publisher.privacy_policy_url` 直指 `PRIVACY.md`，
评委顺着商店页点进来就能看到。

| # | 矛盾 | 处置 |
| --- | --- | --- |
| A-1 | `PRIVACY.md` 两处写「3 个域」，而 manifest 当时只有 1 个 | 改成单域口径，并说明另两个域为何在 v0.5.0 移除 |
| A-2 | `PRIVACY.md` 全文零处披露 `model` 会外发数据，且明文断言「不发送任何数据」——**这句话在当前实现下是错的** | 权限清单 2 项→3 项；「不发送任何数据」拆成三张表（天气 / 城市名 / 模型），逐项写清目的地、触发条件、发出内容 |
| A-3 | 建议 4 的「右上角标记」做在了**时光日记卡**标题行，而那张卡在页面很下方 | 移到月历顶栏 —— 视觉上就是格子的右上角，天气图标实际出现的地方 |
| A-4 | `listing.json` 的 `release_notes` 还是「第四版」文案，通篇只讲天气，一句没提模型 | 整段换 v0.5.0 口径，首句即「模型参与冲突改期，但决定权不在模型手里」 |

---

## 三、实测证据

全部真机宿主（`card-host`），零手改、零 mock：

| 项 | 结果 |
| --- | --- |
| `tools/verify_city.sh` | **12 项断言全过**，宿主 `[E]` = **0** |
| ├ 输入中文城市名 | `val='深圳'`（键盘桥对 UTF-8 无障碍） |
| ├ 坐标落盘 | `wx_city.json` = `lat=22.54554 lon=114.0683`（真实深圳，非北京 39.9042/116.4074） |
| ├ 换城市后缓存 | 清空并按新坐标回填 37 行（30 天历史 + 7 天预报），时间戳晚于坐标写入 |
| └ 顶栏横向预算 | 城市按钮 60px，翻月三按钮 `<` `·` `>` 均 26px 完整 |
| `tools/run_conflict.sh` | **21/21 PASS**，宿主 `[E]` = **0** |
| 往返无损 | 新增 0 / 改期 0 / 跳过 4（导出 ICS 原样再导入） |
| `tools/shots.sh` | **SHOTS PASS**（首次全绿，见 §4） |
| 静态门禁 | brace / quotes / deps / fncalls / paintfix / btnfocus 全过 |

---

## 四、顺手修掉的既有缺陷

### `tools/shots.sh` 长期有 3 条 FAIL，从没绿过

- **症状**：`找不到按钮「详情」`、`找不到按钮「应用建议」`。
- **真因**：脚本在第 03 步之后**缺一次向下滚动**。冲突条在页面下方，
  `/snap` 只返回**视口内**控件 ⇒ 不滚就等于「按钮不存在」。
- **为什么没人发现**：脚本自己在收尾判 `FAIL`，说明它一直红着；
  而收尾的 FAIL 匹配只认行首的 `FAIL`，这几条打的是 `  ★ FAIL …`（带缩进和 ★）。
- **后果比测试本身严重**：`04-conflict-detail` / `05-after-advice` 两张商店截图
  **内容是错的** —— 详情没展开就截了。
- **修法**：按 `run_conflict.sh` 里已记录的方向补滚动（冲突条要 `scroll 400` 向下），
  并在 05 之后滚回顶部（状态条在页头）。

### 其余三处

- `01-list` 截图前等 3 秒让天气上屏 —— 否则格子里只有节日标记、没有天气图标，
  而顶栏那个城市按钮会显得毫无来由。
- `fest_btn` 的 `margin: Inset{right: 6}` 让它在 `flow: Right` 下 **y 偏移 3px**
  （349 vs 同行 352），顶栏肉眼可见不在一条线上。父容器已有 `spacing: 6`，margin 多余。
- 新增 `e2e.py` 子命令 `city_panel` / `city_cancel`。

---

## 五、这轮踩到的宿主机制（都是实测换来，不是推断）

| # | 机制 | 症状 |
| --- | --- | --- |
| 1 | **顶层 `let x = 默认值` 是「每次 eval 都重新赋值」，不是初始化一次** | 状态变量声明若排在 `load()` 之后，用户刚点开的面板会被下一次 re-eval 静默重置 —— 表现为「面板自己关了」，一度被误判成走了成功路径 |
| 2 | `to_f64()` 不能用在 number 上（含 `parse_json` 的结果） | `method to_f64 not found on number` |
| 3 | `to_chars()` 返回 **U32 码点数组**，不是字符串数组 | 逐字符遍历拼出 `"83104101110122104101110"`（S=83,h=104…），geocode 查不到任何城市 |
| 4 | `len()` 数的是**字节**不是字符 | `len("Shenzhen")` = 8（9 个字母） |
| 5 | `sys.geocodenum` 同步阻塞 + fetch 异步 ⇒ **首次必然 -9999**；而 Splash 没有同步延时原语 | 放在 `load()` 开头会把整个 `load()` 卡死；只能靠 `start_timeout` 自动重试（用户仍只需点一次） |
| 6 | 「最右边界没超视口」≠「没挤掉东西」 | 顶栏城市按钮 92px 时，最右仍是 392 < 412，但翻月的 `>` 已从 26px 被压到 12px；116px 时直接消失 |

第 1 条尤其值得记：**它不是本轮引入的**，而是这个语言的一个根本性质 ——
任何新增状态变量都必须声明在 `load()` 之前。

---

## 六、发布件与准入

| 字段 | 值 |
| --- | --- |
| Bundle blake3 | `2d87d36d80d7e1886ff83f3bd9e2047d6352f15db5067bc835bb5ebf4ba352c0` |
| Signature (Ed25519) | `12146f93c520a587c162467ab201e6e310bbdac8…` |
| Publisher key id | `OMA`（沿用 v0.4.0 / v0.5.0 的同一把钥匙） |
| 公钥 | `46b11cc186e7a8ea8688c9d5a246caeaa27e6e0c8ba2986547d7511c0b872380` |
| 密钥位置 | `~/.octosense/oma-publisher.key`（仓库外） |

**`hub check` 结果（2026-10-10）**：

```
com.oma.octosense.calendar 0.5.1 — PASSED
  grants: capabilities {"model", "net", "storage"},
          hosts {"api.open-meteo.com", "geocoding-api.open-meteo.com"},
          storage 16777216 bytes, agent none
```

对照组 `hub check bundle`（不带 `--publisher-key`）→
`refused: publisher key "OMA" is not registered with this hub`。

复核命令：

```bash
hub check bundle --publisher-key OMA=46b11cc186e7a8ea8688c9d5a246caeaa27e6e0c8ba2986547d7511c0b872380
```

⚠️ 五处一致性（仓库 · GitHub commit · Release 下载件 · `hub check` · zip sha256）
**在本文件写下时只完成了前两处**；Release 资产与 zip sha256 待发布后回填核对。

## 七、与 v0.5.0 的关系

- 模型参与改期的部分**没有变化**，七道闸仍然全部生效；
- 往返无损 `0/0/4` 在加了 AI 层与城市层之后**依然成立**（实测）；
- 复赛提交截止 **10/13 23:59**。
