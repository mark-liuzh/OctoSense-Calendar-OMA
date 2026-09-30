# OctoSense 日历 · 吉祥物动画调研

> 队伍 OMA · 2026-09-28
> 目标：为 OctoSense 日历找一款**可动画、可授权、可落地**的吉祥物。
> 结论：**已选定 —— Noto Animated Emoji 的 `:octopus:`（🐙），WebP 动画格式**。

---

## 一、结论先行

**推荐：Google Noto Animated Emoji 的章鱼（Codepoint `1F419`），导出为 48 帧循环 WebP 动画。**

理由三条，全部经实测验证：

| 维度 | 实情 |
| --- | --- |
| **动画是真的** | 源文件 48 帧、60 fps、时长 1.6s 的无缝循环，不是静态图 |
| **格式被宿主接受** | `.webp` 正是宿主资源服务的 MIME 白名单之一（见第三节） |
| **体积可接受** | 128px 版本 **229 KiB**，压到卡片单文件上限之内，且极贴近 16 MiB 的 jail 上限 |

**为什么是章鱼**：OctoSense 整个生态的代号都是 `octo*`（octos、octoscode、OctoLoop、OctoScript、OctoSense）。🐙 是这个生态系统**自带的、无需解释的**身份符号——不是我们外挂一个吉祥物，而是把这个生态的既有符号**动画化**。

---

## 二、候选调研：我看了哪些，为什么否掉

### 2.1 真正的约束不是"好不好看"，是"宿主收不收"

调研过程中最有价值的发现是：**这题的决定因素不是美术，是准入规则。** 生态对资源的限制是硬编码的，任何方案必须先过这一关。

从 `OctoSense-App-Hub` 的 `crates/app-policy/src/assets.rs` 读到两条硬规则：

```rust
// 1. MIME 白名单 —— 只有这五种扩展名会被正确标注类型
fn mime_for(file: &Path) -> &'static str {
    match file.extension().and_then(|e| e.to_str()).unwrap_or("") {
        "svg" => "image/svg+xml",
        "png" => "image/png",
        "jpg" | "jpeg" => "image/jpeg",
        "webp" => "image/webp",
        "json" => "application/json",
        _ => "application/octet-stream",
    }
}

// 2. 卡片资源重写白名单 —— 只有这四种后缀会被改写成可访问 URL
if !text.contains("://") && (text.ends_with(".svg") || text.ends_with(".png")
    || text.ends_with(".webp") || text.ends_with(".jpg")) {
    *text = format!("{origin}{}", text.trim_start_matches('/'));
}
```

这两段代码**直接否决了 Lottie 路线**，理由见下。

### 2.2 逐条否决记录

| 候选 | 问题 | 判定 |
| --- | --- | --- |
| **Lottie JSON**（Noto 官方也提供） | ⛔ **双重排除**：① 卡片资源重写白名单里**没有 `.json`**，写了也不会被改写成 URL；② L0 卡片规范明文写死「**L0 cannot express a card that … drives its own animation loop**」——每帧驱动动画是 L0 的语言能力之外 | ❌ 否 |
| **Animated GIF** | ⛔ `.gif` 不在 MIME 白名单，也不在重写白名单 → 会被当成 `application/octet-stream`，且卡片引用不到 | ❌ 否 |
| **LottieFiles 等第三方动画站** | ⛔ 许可不允许。其服务条款明文：免费版**禁止商业使用**；且「**Cannot redistribute as standalone animation files**」——与本项目 Apache-2.0 开源仓库的再分发要求直接冲突 | ❌ 否 |
| **Microsoft Fluent Emoji** | MIT 许可，但对**动画**版本而言资产覆盖差、且我们真正想要的那个符号不在其中；静态版是 SVG，无动画价值 | ⚠️ 备选 |
| **TGS（Telegram 贴纸）** | ⛔ gzip 压缩的 Lottie，同一套 L0 限制，且需额外解压器（宿主明确不做透明解压） | ❌ 否 |
| **APNG** | 理论上可行，但**宿主 MIME 白名单无 `.apng`**，且体积显著大于 WebP | ❌ 否 |
| **自绘 SVG + `nav_period` 式宿主动画** | 需要宿主支持「自持动画」的角色位。规范里 `nav_period`、`TempBar` 这类是**宿主内置角色**，商店应用**无法自定义新角色**（需要改宿主并重新构建，超出商店应用能力） | ❌ 否（可用于原型演示，不能作为交付形态） |

### 2.3 唯一可行解

**WebP 动画**是白名单里**唯一一个原生支持多帧动画**的格式：

- ✅ `.webp` 在 MIME 白名单 → 类型正确
- ✅ `.webp` 在卡片资源重写白名单 → `Photo(src: mascot.webp)` 能被宿主改写成 loopback URL
- ✅ 逐帧压缩，40–60% 体积下降
- ✅ 48 帧真动画，循环播放
- ⚠️ 但工作量有代价：我们需自带逐帧解码播放逻辑（见第五节）

---

## 三、宿主机制：为什么必须是这个格式

这三段机制决定了整条技术路线，值得单独记下来。

### 3.1 卡片资源只能走 loopback HTTP

`assets.rs` 开头的注释把规则说得很清楚：

> The lowering rule is that a card's vectors must come from a **loopback HTTP origin**: a path on disk is **refused outright**. A bundle, meanwhile, **must not name an outside origin**.
> Both rules hold at once only if the **HOST serves the app's bytes**.

于是宿主的做法是：**每个运行中的应用起一个绑定 `127.0.0.1` 随机端口的 HTTP 服务**，只服务该应用 bundle 目录内的文件，然后把卡片 bundle 里的相对路径改写成 `http://127.0.0.1:<port>/...`。

**推论**：吉祥物素材必须**打进 bundle**，不能引外部 CDN。

### 3.2 没有透明解压

宿主服务文件的逻辑是**裸读字节直接发出**：

```rust
std::fs::File::open(&file).and_then(|mut f| f.read_to_end(&mut bytes))
```

—— 没有 `Content-Encoding`、没有 gzip 解压。**所以不能靠预处理压缩来绕开体积限制**：文件在磁盘上多大，就占多大。

（附带安全细节：`resolve()` 会 `canonicalize` 并校验 `starts_with(canonical_root)`，`..`、绝对路径、符号链接全部拒绝。防穿越做得扎实。）

### 3.3 L0 不驱动动画，但"帧由宿主演"是既有机制

L0 卡片规范里有一句关键说明，解释了为什么这题有解：

> `nav_period` means **the widget owns its own animation**, so the moving vehicle is not the card's concern either.

即：**卡片声明数据，宿主角色负责动画**。问题是这类角色是**宿主内置的固定目录**（`WeatherIcon`、`TempBar`、`SunArc`、`MoonPhase`、`AqiContour`、`StockPlot`），商店应用**不能新增角色位**（`octoscript-render` 的 tag 表是固定的）。

所以吉祥物动画不能走"自定义角色"这条路，只能走**已存在的图像节点 + 多帧资源**这条路 —— 也就是 WebP。

---

## 四、实测数据

### 4.1 素材来源与真实性核验

官方动画集合站点 `googlefonts.github.io/noto-emoji-animation`，索引 `data/api.json`（158 KB，**881 个图标**）。其中确证存在：

```
codepoint 1f419 · name emoji_u1f419 · tags [":octopus:"] · category "Animals and nature"
```

真实资产地址（均已实测可下载）：

| 格式 | URL | 体积 |
| --- | --- | --- |
| Lottie JSON | `https://fonts.gstatic.com/s/e/notoemoji/latest/1f419/lottie.json` | 229.0 KiB |
| **WebP 动画 512px** | `.../1f419/512.webp` | **406.2 KiB** |
| GIF 512px | `.../1f419/512.gif` | 478.1 KiB |
| SVG（静态） | `.../1f419/emoji.svg` | 6.4 KiB |

源 WebP 实测属性：**512×512 · 48 帧 · 60 fps · 无缝循环**。

### 4.2 Lottie 的结构（为我们自己压缩时参考）

```
v=5.8.1  fr=60  ip=0  op=96  w=h=1024  layers=15  assets=0  markers=null
```

15 个图层、零外部依赖、纯矢量 —— 结构很干净。压缩能力实测：**229 KiB → gzip 后 38.8 KiB（17.5%）**。

但如 2.2 所述，JSON 进不了卡片。**这个压缩能力目前用不上**，除非将来宿主支持。

### 4.3 WebP 动画体积矩阵（逐帧重压缩，48 帧全部保留）

| 尺寸 | 质量 | 体积 | 占源比 | 帧数 |
| --- | --- | --- | --- | --- |
| 192px | 80 | 406.4 KiB | 100% | 48 |
| 192px | 60 | 349.2 KiB | 86% | 48 |
| 128px | 80 | 264.8 KiB | 65% | 48 |
| **128px** | **60** | **229.2 KiB** | **56%** | **48** |
| 96px | 80 | 196.7 KiB | 48% | 48 |
| **96px** | **60** | **170.1 KiB** | **42%** | **48** |
| 80px | 50 | 132.8 KiB | 33% | 48 |
| **48px** | **75** | **84.0 KiB** | **21%** | **48** |
| 48px | 50 | 75.1 KiB | 18% | 48 |
| 64px 无损 | — | 230.8 KiB | 57% | 48 |
| 32px 无损 | — | 86.7 KiB | 21% | 48 |

### 4.4 与体积上限的关系（关键约束）

| 上限 | 值 | 128px 版本占用 |
| --- | --- | --- |
| **卡片 bundle 单文件** | **256 KiB** | **89%** ⚠️ |
| jail 总量（商店应用） | 16 MiB | 1.4% |
| 卡片 bundle 整体 | 待确认 | — |

**⚠️ 需要注意**：卡片 bundle 单文件上限若确为 256 KiB，那么 229 KiB 的 128px 版本已经吃掉 **89%** 的额度，留给其它素材（图标、插图、示例图）的空间非常紧。

**分级方案建议**：

| 用途 | 尺寸 | 体积 | 说明 |
| --- | --- | --- | --- |
| **卡片内**（L0） | 48px | 84 KiB | 满足单文件上限，剩余额度充裕 |
| **应用内**（`main.splash`） | 96–128px | 170–229 KiB | 应用侧不受卡片单文件限制，可用更大 |
| 静态兜底 | SVG | 6.4 KiB | 动画不可用时降级 |

---

## 五、落地需要自己做的部分

选定了素材，但要真正跑起来还有一段工程，必须诚实说明。

### 5.1 需要自实现的解码器

宿主**不提供** WebP 动画播放。应用侧要自己写：

1. 读 bundle 内的 `.webp` 字节
2. 解析 RIFF/WEBP 容器，取出 `ANMF` 帧块
3. **VP8X/VP8L 有损帧解码** ← 这是真正的难点，纯脚本实现不现实
4. 按 `duration` 逐帧送画布

**这就是之前记录的「卡在 Rinx / makepad Windows 构建」那条线** —— 单通道共享帧缓冲（Single Channel Shared Frame Buffer）本就在我们原型里，而这个章鱼动画正好可以复用它。

### 5.2 更现实的降级路径

| 方案 | 可行性 | 说明 |
| --- | --- | --- |
| **A. 宿主持有动画能力**（复用 SCSFB 通道） | 🟡 待实测 | 若可行，最干净 |
| **B. 预解码为逐帧 PNG 序列** | 🟢 可行 | 48 帧 × 约 12 KiB（96px PNG）≈ 576 KiB，但在 **jail 16 MiB 内完全放得下**；代价是要自己写帧调度 |
| **C. SVG 静态 + 宿主侧过渡** | 🟢 保底 | 用 `nav_period` 那类宿主动画机制给静态图加运动感 |

**B 方案是被低估的一条**：预解码之后完全绕开 WebP 解码难题，只留下"按时间换帧"这种简单逻辑。

**延迟预算也支持这个结论**：128px 版 229 KiB ÷ 1.6s ≈ **143 KB/s**，即使逐帧现解也毫无压力。

---

## 六、授权合规（Apache-2.0 仓库必须能过）

这是本项目最容易出事的地方，因为**主仓库是 Apache-2.0 开源仓库**，素材许可能不能跟着走是硬门槛。

| 集合 | 许可 | 可再分发 | 能否进 Apache-2.0 仓库 |
| --- | --- | --- | --- |
| **Noto Animated Emoji** | **CC BY 4.0** | ✅ | ✅ **可以，需注明出处** |
| Noto Color Emoji（静态） | OFL-1.1 | ✅ | ✅ |
| Microsoft Fluent Emoji（静态） | MIT | ✅ | ✅ |
| Twemoji | CC BY 4.0 | ✅ | ✅ |
| Blobmoji | Apache-2.0 | ✅ | ✅ |
| **LottieFiles 免费库** | Lottie Simple License | ❌ **禁止作为独立文件再分发** | ❌ **否** |
| **Fluent Emoji "Animated" 仓库** | **Personal Use Only** | ❌ | ❌ **否** |

**两个必须避开的坑**：

1. **LottieFiles 免费动画**：可商用，但**禁止再分发独立文件**，且禁止"编译或抓取动画以创建竞争性服务"。放进公开源码仓库就是再分发 → **违规**。
2. **名为 "Animated Fluent Emojis" 的那个 GitHub 仓库**：**仅限个人使用**（Personal Use Only），很多人误以为它是 MIT —— 它和微软官方的 `fluentui-emoji`（MIT，仅静态）**不是一回事**。

**Noto Animated Emoji 采用 CC BY 4.0：需在应用 About 页保留一行署名**，不要求逐项标注，也不禁止商用、不要求 ShareAlike、不影响我们自己的 Apache-2.0 许可。

> 待办：在仓库 `NOTICE` / `THIRD-PARTY.md` 记录素材来源、codepoint、许可与下载日期；在应用 About 页放署名。

---

## 七、下一步

1. **确认体积上限**：核实卡片 bundle 的单文件上限到底是 256 KiB 还是别的值 —— 这直接决定卡片内用 48px 还是 128px
2. **实测方案 A**：验证宿主能否复用现有动画通道播放 WebP，这是最省事的方向
3. **准备方案 B 兜底**：把 128px WebP 预解码为 PNG 序列（jail 内放得下），自己写帧调度
4. **补 `THIRD-PARTY.md`**：记录 CC BY 4.0 署名，赶在首次推送素材前完成
5. **视觉一致性**：章鱼是扁平风格 emoji，需确认它与日历主视觉（暖色城市插画风）是否协调；若不协调，考虑仅用于**状态提示**（Agent 思考中 / 已生成提案 / 等待回复）而非主视觉点缀

---

## 附：已落盘素材

```
prototype/assets/mascot/
├── final/
│   ├── octo-mascot-128.webp      229.2 KiB  48帧  ← 应用内主用
│   ├── octo-mascot-96.webp       170.1 KiB  48帧
│   ├── octo-mascot-48.webp        84.0 KiB  48帧  ← 卡片内用
│   └── octo-mascot-static.svg      6.4 KiB  静态兜底
└── candidates/                   完整体积矩阵，用于选型比对
    ├── octopus-512.webp          406.2 KiB  原始源文件
    ├── octopus-lottie.json       229.0 KiB  （格式受限，仅存档）
    ├── octopus.svg                 6.4 KiB
    ├── mascot-{48,64,80,96,128,192}-q{50,60,75,80}.webp
    └── ll-{32,48,64}.webp                   无损版本对照
```

预览页：`prototype/assets/mascot/preview.html`
