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

## 2. 演示视频配乐（Bensound「Sunny」）

[README](README.md#演示视频) 里的两个演示视频用了一段第三方背景音乐。它**不随应用分发**
（不在 `bundle/` 里），但视频文件本身进了本仓库，因此按许可要求在此署名。

| 项 | 内容 |
| --- | --- |
| 作品 | **Sunny** |
| 作者 / 来源 | Bensound · <https://www.bensound.com> |
| 许可 | Bensound Free License —— 免费使用**必须署名**，且不得再分发原始音频<br><https://www.bensound.com/licensing> |
| 使用位置 | `docs/media/octosense-demo-3min.mp4`、`docs/media/octosense-demo-1min30.mp4` 的背景音轨 |
| 原始规格 | MP3 · 320 kb/s · 48 kHz · 立体声 · 2:20 |

### 本项目所做的改动

| 改动 | 说明 |
| --- | --- |
| 裁剪与循环 | 按视频时长（3:27 / 1:39）裁剪并循环，**未修改旋律、未重新编曲** |
| 音量 | 衰减为铺底（约 −9 dB 相对旁白），避开中文语音频段，不抢旁白 |

### 署名（按 Bensound 许可要求的格式）

> Music by Bensound.com
> https://www.bensound.com

同一署名也出现在 [README 的「演示视频」一节](README.md#演示视频)。

### 为什么原始音频没有进仓库

Bensound 的免费许可允许在作品中使用，但**不允许再分发音频文件本身**。因此：

- 仓库里只有**已混音的成品视频**，没有单独的 `sunny-source.mp3`；
- 录屏脚本 [`tools/record_demo.py`](tools/record_demo.py) 只在本地找到该文件时才用它作配乐，
  找不到时**回退为程序合成的铺底音**（`aevalsrc`），因此 clone 本仓库不会得到 Bensound 的音频副本。

---

## 3. 宿主与运行时（依赖，不随本包分发）

| 名称 | 许可 | 关系 |
| --- | --- | --- |
| OctoSense App Hub / `card-host` | Apache-2.0 | 应用运行其上的隔离宿主，由使用者自行构建，本仓库不包含其代码 |
| Makepad | MIT / Apache-2.0 | 宿主内部使用的 UI 引擎，间接依赖 |

## 4. 开发期工具（不随应用分发）

实测脚本（`tools/run_*.sh`、`tools/e2e.py` 等）只使用 Python 3 标准库与 `curl`，**没有第三方依赖**。

唯一的例外是录屏工具 [`tools/record_demo.py`](tools/record_demo.py)（生成 `docs/media/` 里的两个演示视频），
它额外用到三个**开发期**依赖：

| 包 | 许可 | 用途 |
| --- | --- | --- |
| [`Pillow`](https://python-pillow.org/) | MIT-CMU | 生成字幕条与首尾卡 |
| [`imageio`](https://imageio.readthedocs.io/) + [`imageio-ffmpeg`](https://github.com/imageio/imageio-ffmpeg) | BSD-2-Clause | 写出 MP4、混音（后者随包提供 ffmpeg 二进制，因此无需 brew） |
| [`NumPy`](https://numpy.org/) | BSD-3-Clause | 帧转 RGB 数组 |

三者都只用于**开发期生成视频**，**不进入 `bundle/`**，因此不影响应用包的内容与许可。

---

如发现署名或来源标注有误，请开 issue：
<https://github.com/mark-liuzh/OctoSense-Calendar-OMA/issues>
