# Windows 工具链落地报告

> OctoSense 日历 · 队伍 OMA · 2026-09-28
> 目的：回答「Windows 上到底能不能干活」这个问题。
> 结论：**能。已全线跑通——应用被承载、脚本被求值、画面被渲染、截图可取证。**

---

## 一、结论先行

**Windows 上能干活，而且已经全线跑通。**

| 能力 | 状态 | 证据 |
| --- | --- | --- |
| Rust 工具链 | ✅ | 1.98.1，MSVC 链接器可用 |
| 五仓库锁定版本 | ✅ | `setup-native.py --check` → exit 0 |
| **官方商店门禁 `hub`** | ✅ | 编译成功，`hub.exe help` 输出完整命令表 |
| **应用宿主 `card-host`** | ✅ | 编译成功（24 MB），**已成功承载并渲染应用** |
| **应用创建 `octo new`** | ✅ | 已产出 `D:\Projects\Apps\octosense-calendar` |
| **应用运行 `octo run`** | ✅ | `admitted` → `jailed` → `[SPLASH] eval` → `first frame drawn` |
| **截图验证** | ✅ | `octo shot` 出 39 KB PNG，**中文正常渲染** |
| `octo doctor` | ✅ | 全绿，输出 `ready: tools/octo new <dir> && tools/octo run <dir>/bundle` |

**一句话**：Windows 是官方**未验证**平台（原文：*"Code paths are retained from upstream but not validated here."*），
但实际能跑。代价是要绕三个坑，都已在下面给出解法。

---

## 一点五、跑通的实证

`octo doctor` 输出：

```
octo doctor  (repo D:\Projects\OctoScript-App-Design-Flow)
  [ok]   python 3.13.14
  [ok]   App Hub checkout D:\Projects\OctoSense-App-Hub
  [ok]   hub: ...\hub.exe  (from $OCTO_HUB)
  [ok]   card-host: ...\card-host.exe  (from $OCTO_CARD_HOST)
  [info]   cargo: not on PATH (needed only to build hub and card-host)
  [ok]   template templates\script-app

ready: tools/octo new <dir> && tools/octo run <dir>/bundle
```

应用被承载时的关键日志（**隔离与权限强制全部生效**）：

```
card-host: com.oma.octosense.calendar 0.1.0 admitted —
           capabilities {"storage"}, hosts {}, storage 16777216 bytes, agent none
card-host: isolate jailed at ...\.local-state\com.oma.octosense.calendar
           with 16777216 bytes, 1 capability(ies), 1 host(s),
           20000000 instructions, 67108864 bytes of heap, prompts false — all enforced
[SPLASH] eval: 2153 bytes
ready: first frame drawn
```

### ★ 附赠：完整的远程驱动 API

`card-host` 起了一个本地 HTTP 控制桥（`MAKEPAD_REMOTE=<port>`），
**这等于白送一套自动化测试工具**：

| 路由 | 用途 |
| --- | --- |
| `/snap` | **控件矩形坐标**，可直接用于点击 ← 最有价值 |
| `/g?raw=1` | 抓帧（PNG 字节） |
| `/gseq?n=8&every_ms=50` | 逐帧抓，适合看动画 |
| `/m?k=click&x=&y=` | 鼠标（`move/down/up/click/scroll`） |
| `/k?t=TEXT` | 输入文本 |
| `/k?k=down&c=KeyA` | 按键（`Escape` / `ReturnKey` / `Tab` / `F1` / `Key1` …） |
| **`/drop?path=&x=&y=`** | **模拟文件拖放** —— 自动化测 ICS 导入正合用 |
| `/log?n=50` | 日志增量 |
| `/quit` | 退出 |

**对我们的价值**：把「导入 ICS → 看到冲突」这个演示流程**脚本化跑一遍并留截图**，
不依赖人去点窗口。**评审要求的"可核对的操作结果"可以直接由这套 API 产出证据。**

**注意**：`card-host` 会随启动它的 shell 一起退出 ——
后台长驻要在**同一个 shell 进程**内完成"启动 + 操作 + 截图"。

**注意**：控件要能被 `/snap` 精确定位，**必须在 `main.splash` 里给它起 id**
（`entry := TextInput{...}`）。没起名的控件 id 显示为 `-`。

---

## 二、三个坑与解法（★ 最有价值的部分）

### 坑 1：crate 的 build script 找不到 `rustc`

**症状**：
```
error: failed to run custom build command for `num-traits v0.2.19` (exit code: 101)
thread 'main' panicked at autocfg-1.5.1/src/lib.rs:160:20:
called `Result::unwrap()` on an `Err` value: Error { kind: Io(Error { kind: NotFound,
message: "program not found" }) }
```
后来又撞到 `httparse v1.10.1` 的同款错误。

**根因**：一大批 crate 的 build script 这么写——

```rust
let rustc = env::var_os("RUSTC").unwrap_or(OsString::from("rustc"));
Command::new(rustc).arg("--version").output().expect("...")
```

缺省退化成裸词 `rustc` 去 PATH 找，而 PATH 上只有 **`.cargo/bin/rustc.exe`——rustup 的 0 字节 shim**，
在沙箱化的 git-bash 里失效。

**✅ 解法（一次解决全部同类问题）**：

```bash
export RUSTC="$HOME/.rustup/toolchains/stable-x86_64-pc-windows-msvc/bin/rustc.exe"
export RUSTDOC="$HOME/.rustup/toolchains/stable-x86_64-pc-windows-msvc/bin/rustdoc.exe"
```

**配套必做**：改了影响 build script 的行为后，要清掉缓存的 build script 目录，
否则 cargo 复用旧二进制，补丁不生效：

```bash
rm -rf "$CARGO_TARGET_DIR/release/build/<crate>-<hash>"
```

> ⚠️ 我一开始的做法是改 registry 里 crate 的 `build.rs`（把 autocfg 探针换成
> 直接 `println!("cargo:rustc-cfg=has_total_cmp")`）。
> 那是**错的方向** —— crates.io 上这样写 build script 的包数以千计，打不完的补丁。
> 正确解法是上面两行环境变量。改 registry 的痕迹已备份为 `Cargo.toml.octosense-bak`。

### 坑 2：并行构建导致进程被终止

**症状**：`EXIT=1`，日志里**一个 `error` 都没有**，日志在某个 `Compiling` 行**戛然而止**。

**判别法**：

| 现象 | 含义 |
| --- | --- |
| 有 `error: ...` 且能读到 | 真的编译错误 |
| **exit ≠ 0，日志无 error 且中途截断** | **进程被外部终止** |

**根因**：本机 16 GB 内存，WorkBuddy 自身常驻约 1.5 GB。
`makepad-widgets` / `makepad-platform` / `card-host` 都是巨型链接目标，
并行构建时峰值叠加，进程被杀。

**✅ 解法**：

```bash
export CARGO_BUILD_JOBS=1          # 关键：串行，把峰值压到最低
export RUSTFLAGS="-C debuginfo=0"  # 关键：不产调试信息，显著降链接内存
```

**★★ 并且：一次只构建一个包。**

```bash
"$TC/cargo.exe" build --release -p octosense-app-hub    # 先这个（4 分钟成功）
"$TC/cargo.exe" build --release -p octosense-card-host  # 再这个（增量复用，起点高）
```

两个巨型链接目标**同时**构建必然失败。分开就不一样。

> 已验证 cargo 的增量编译有效：每次被中断后重启都从上次停的位置继续，**不会白干**。

### 坑 3：产物带 `.exe`，`tools/octo` 找不到

**症状**：`octo doctor` 报 `[fail] hub not found`，但 `hub.exe` 明明就在那儿。

**根因**：`tools/octo` 的 `find_binary()`（第 87–101 行）查的是 `d / name`，
即 `hub` / `card-host` **裸名**。Windows 产物是 `hub.exe` / `card-host.exe`。

**✅ 解法**（用环境变量绕开，不改官方脚本）：

```bash
export OCTO_HUB="D:/Projects/.cargo-target/octosense/release/hub.exe"
export OCTO_CARD_HOST="D:/Projects/.cargo-target/octosense/release/card-host.exe"
```

`find_binary` 优先读 `$OCTO_HUB`（第 84–90 行），显式给路径就绕过了后缀问题。

验证：
```
[ok]   hub: D:\Projects\.cargo-target\octosense\release\hub.exe  (from $OCTO_HUB)
```

---

## 三、一键构建脚本

已落在 `D:\Projects\build-tools.sh`（本机专用，**不进任何仓库**）：

```bash
#!/usr/bin/env bash
set -euo pipefail

TC="$HOME/.rustup/toolchains/stable-x86_64-pc-windows-msvc/bin"
export RUSTC="$TC/rustc.exe"          # 坑 1
export RUSTDOC="$TC/rustdoc.exe"
export CARGO_TARGET_DIR="D:/Projects/.cargo-target/octosense"
export CARGO_BUILD_JOBS=1             # 坑 2
export RUSTFLAGS="-C debuginfo=0"     # 坑 2

cd /d/Projects/OctoSense-App-Hub
"$TC/cargo.exe" build --release -p octosense-app-hub
"$TC/cargo.exe" build --release -p octosense-card-host
```

配套环境变量（用 `octo` 时）：`OCTO_HUB` / `OCTO_CARD_HOST`（坑 3）。

---

## 四、环境事实（避免重复排查）

| 项 | 值 |
| --- | --- |
| OS | Windows，**裸机**（非 WSL） |
| 内存 | 15.5 GiB（**构建的瓶颈**） |
| 交换 | 38 GiB（几乎未用，说明不是换页问题） |
| C 盘 | 27 GB 可用（**代码不放这里**） |
| D 盘 | 78 GB 可用，代码在工作盘 |
| Rust | 1.98.1，`stable-x86_64-pc-windows-msvc` |
| 构建目录 | `D:\Projects\.cargo-target\octosense`（约 812 MB） |
| Python | 3.13.12（`octo` 需要 3.9+） |

### 工作区布局（官方要求五仓库同级）

```
D:\Projects\
  OctoScript-App-Design-Flow\   tools/octo + setup-native.py + examples/
  OctoSense-App-Hub\            hub / card-host
  makepad\                      @ d0a9def5
  octoscript-makepad\           @ 99c1e5ee
  octoscript\                   @ 68f6a9df
```

### ⚠️ 两条"别踩"提醒

1. **git-bash 里不能调 rustup shim**。`cargo --version` 会**完全无输出且 rc=0**
   （stdout 被吞，极易误判为"命令不存在"）。必须用真身全路径。
2. **判断构建状态看 `EXIT=`，不要只看日志尾部**。日志截断 ≠ 还在编译，
   可能进程早就死了。

---

## 五、还差什么

| 待办 | 说明 |
| --- | --- |
| 写 ICS 解析器到 `main.splash` | `prototype/ics_parser.splash` 已写好（API 核过源码），待接入应用 |
| 跑 ICS 解析器自测 | `prototype/ics_parser_test.splash` 已写好 |
| 用 `/drop` + `/snap` + `/shot` 做自动化导入演示 | 工具已就绪，可以脚本化产出演示证据 |
| 把演示流程录成 2–3 分钟视频 | 评审材料要求 |

**已解除的风险**：原本担心的"Windows 图形会话跑不了 `card-host`"——**不存在**。
`--hidden` 无头模式工作正常，D3D11 渲染正常，`/g?raw=1` 能抓帧。

**剩余真实风险**：本机 16 GB 内存下**构建很慢**（单包 4–15 分钟），
但只要按 `CARGO_BUILD_JOBS=1` + 分包的姿势走就不会失败。
**构建产物已就位，后续改代码不需要重编 `card-host`**（它只承载，不编译应用逻辑）——
应用是 `.splash` 脚本，**改完直接 `octo run` 即可，无编译步骤**。
这一点和官方说的一致：脚本应用「无编译步骤」，是我们选脚本路线而非 native 路线的最大好处。
