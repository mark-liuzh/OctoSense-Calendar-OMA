# 第三方素材与许可

本仓库自己的代码以 [Apache License 2.0](LICENSE) 发布。下面列出**不属于**本项目、随包分发的第三方素材。

---

## 1. 章鱼吉祥物动画（Noto Animated Emoji）

界面里那只章鱼不是自绘，也不来自第三方素材站，而是 Google Noto 项目的动态 emoji。

| 项 | 内容 |
| --- | --- |
| 作品 | Noto Animated Emoji —— `:octopus:` / 🐙（Unicode `U+1F419`） |
| 版权方 | Copyright Google LLC |
| 来源 | <https://googlefonts.github.io/noto-emoji-animation/> |
| 原始文件 | `https://fonts.gstatic.com/s/e/notoemoji/latest/1f419/512.webp`（动画）<br>`https://fonts.gstatic.com/s/e/notoemoji/latest/1f419/emoji.svg`（静态） |
| 原始规格 | 512×512 · 48 帧 · 60 fps · 无缝循环 |
| 许可 | **Creative Commons Attribution 4.0 International（CC BY 4.0）**<br><https://creativecommons.org/licenses/by/4.0/> |

### 本项目所做的修改

按 CC BY 4.0 的要求，如实说明对原始素材的改动：

| 文件 | 改动 |
| --- | --- |
| `bundle/octo-mascot-96.webp` | 由 512 px 源缩放至 96 px，逐帧重编码（质量 60），**48 帧全部保留** |
| `bundle/octo-mascot-48.webp` | 由 512 px 源缩放至 48 px，逐帧重编码（质量 75），**48 帧全部保留** |
| `bundle/octo-mascot-static.svg` | 原样使用，未修改（动画不可用时的降级素材） |

**未做**：未改配色、未重绘、未与其他素材合成。

### 署名

应用内「关于」页展示以下署名，使用者无需离开应用即可看到：

> 吉祥物素材：Noto Animated Emoji `:octopus:`（U+1F419）
> © Google LLC · CC BY 4.0
> https://googlefonts.github.io/noto-emoji-animation/

### 为什么不用 Lottie，也不用其他素材库

调研过程与排除理由记录在 [`docs/mascot-research.md`](docs/mascot-research.md)，结论是：

- **Lottie JSON 用不了**：宿主资源服务的 MIME 与卡片资源重写白名单里都没有 `.json`，
  引用了也不会被改写成可加载的 URL。
- **第三方动画站用不了**：LottieFiles 免费版条款明文禁止再分发独立动画文件，
  与本仓库的 Apache-2.0 开源再分发要求直接冲突。
- **WebP 是唯一可行解**：它是宿主白名单里唯一原生支持多帧动画的格式，
  因此源 Lottie 被导出为 48 帧 WebP。

### 分发方式

三份素材都以**文件形式随 bundle 打包**，运行时由宿主从本地读取。
应用**不申请网络权限**，不会在使用时从字体 CDN 拉取素材，因此离线可用，
也不构成对 `fonts.gstatic.com` 的运行时依赖。

---

## 2. 宿主与运行时（依赖，不随本包分发）

| 名称 | 许可 | 关系 |
| --- | --- | --- |
| OctoSense App Hub / `card-host` | Apache-2.0 | 应用运行其上的隔离宿主，由使用者自行构建，本仓库不包含其代码 |
| Makepad | MIT / Apache-2.0 | 宿主内部使用的 UI 引擎，间接依赖 |

## 3. 开发期工具（不随应用分发）

实测脚本（`tools/*.sh`、`tools/*.py`）只使用 Python 3 标准库与 `curl`，
**没有第三方依赖**，也不进入 `bundle/`，因此不影响应用包的内容与许可。

---

如发现署名或来源标注有误，请开 issue：
<https://github.com/mark-liuzh/OctoSense-Calendar-OMA/issues>
