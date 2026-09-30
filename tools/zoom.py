#!/usr/bin/env python3
"""放大 PNG 局部 + 采样像素颜色（纯标准库，不依赖 Pillow）

用法:
  python tools/zoom.py <in.png> <out.png> <x> <y> <w> <h> [scale]
  python tools/zoom.py <in.png> --probe x1,y1 x2,y2 ...     # 只打印色值

为什么需要它：宿主的 /snap 快照**不带颜色**（只有 i / ty / r / w），
「放假是绿点、照常上班是黑点、调休是赤陶点」这类断言拿不到证据，
只能回读截图像素。本机没装 Pillow，而截图是宿主直接吐的 PNG
（8 位 RGB/RGBA、无隔行），所以这里自带一个最小解码器。

支持：位深 8、颜色类型 2(RGB) / 6(RGBA)、filter 0~4。够用即可。
"""
import io
import struct
import sys
import zlib


def read_png(path):
    data = io.open(path, "rb").read()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "不是 PNG"
    pos = 8
    w = h = bitd = ctype = None
    idat = []
    while pos < len(data):
        (ln,) = struct.unpack(">I", data[pos:pos + 4])
        typ = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + ln]
        pos += 12 + ln
        if typ == b"IHDR":
            w, h, bitd, ctype, comp, filt, inter = struct.unpack(">IIBBBBB", body)
            assert bitd == 8, "只支持 8 位"
            assert inter == 0, "不支持隔行"
        elif typ == b"IDAT":
            idat.append(body)
        elif typ == b"IEND":
            break
    raw = zlib.decompress(b"".join(idat))
    ch = {2: 3, 6: 4, 0: 1, 4: 2}[ctype]
    stride = w * ch
    out = bytearray(h * stride)
    prev = bytearray(stride)
    p = 0
    for y in range(h):
        f = raw[p]
        p += 1
        line = bytearray(raw[p:p + stride])
        p += stride
        if f == 1:
            for i in range(ch, stride):
                line[i] = (line[i] + line[i - ch]) & 0xFF
        elif f == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif f == 3:
            for i in range(stride):
                a = line[i - ch] if i >= ch else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 0xFF
        elif f == 4:
            for i in range(stride):
                a = line[i - ch] if i >= ch else 0
                b = prev[i]
                c = prev[i - ch] if i >= ch else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 0xFF
        out[y * stride:(y + 1) * stride] = line
        prev = line
    return w, h, ch, bytes(out)


def px(w, ch, buf, x, y):
    o = (y * w + x) * ch
    return (buf[o], buf[o + 1], buf[o + 2])


def write_png(path, w, h, pixels):
    raw = b"".join(b"\x00" + pixels[y * w * 3:(y + 1) * w * 3] for y in range(h))

    def chunk(typ, body):
        return (struct.pack(">I", len(body)) + typ + body
                + struct.pack(">I", zlib.crc32(typ + body) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    io.open(path, "wb").write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
                              + chunk(b"IDAT", zlib.compress(raw, 9))
                              + chunk(b"IEND", b""))


def main():
    src = sys.argv[1]
    w, h, ch, buf = read_png(src)

    # ⚠️ 截图不是 1:1：宿主 `/g?raw=1` 会把 412x892 的窗口按设备像素比放大
    #    （实测 721x1561 = 1.75x，即 DPI 缩放）。而 /snap 给出的 r 坐标是
    #    **窗口逻辑像素**。不对齐这一步就会全采到白底，白忙一场。
    sc_auto = round(w / 412.0, 4)
    if abs(sc_auto - round(sc_auto)) < 0.01 and round(sc_auto) >= 1:
        sc_auto = round(sc_auto)

    if sys.argv[2] == "--probe":
        print("size %dx%d ch=%d  缩放=%.4g（窗口逻辑尺寸 412x892）" % (w, h, ch, sc_auto))
        print("以下坐标按**窗口逻辑像素**输入，输出是实际采样到的那一点：")
        for spec in sys.argv[3:]:
            x, y = [int(v) for v in spec.split(",")]
            sx, sy = int(round(x * sc_auto)), int(round(y * sc_auto))
            sx = min(max(sx, 1), w - 2)
            sy = min(max(sy, 1), h - 2)
            cols = [px(w, ch, buf, sx + dx, sy + dy)
                    for dx in (-1, 0, 1) for dy in (-1, 0, 1)]
            cols.sort()
            print("  (%4d,%4d) -> 像素(%4d,%4d)  中心=#%02x%02x%02x  邻域中位=#%02x%02x%02x"
                  % (x, y, sx, sy, *px(w, ch, buf, sx, sy), *cols[len(cols) // 2]))
        return

    out = sys.argv[2]
    x, y, cw, chh = [int(v) for v in sys.argv[3:7]]
    sc = int(sys.argv[7]) if len(sys.argv) > 7 else 6
    # ⚠️ 必须按**实际像素**逐点放大（2026-09-30 修）：
    #    之前是「按逻辑坐标取 cw 个采样点，再横向/纵向各复制 sc 次」——
    #    逻辑区 100px 在 1.75 缩放下其实是 175 个实际像素，硬压成 100 列再放大
    #    会漏掉笔画（数字/小圆点经常整条消失），看起来像「整块白」或「瓦片重复」。
    #    现在：先算出逻辑区对应的实际像素矩形，逐实际像素输出 sc×sc 块。
    ax0 = max(0, int(round(x * sc_auto)))
    ay0 = max(0, int(round(y * sc_auto)))
    ax1 = min(w, int(round((x + cw) * sc_auto)))
    ay1 = min(h, int(round((y + chh) * sc_auto)))
    aw, ah = max(1, ax1 - ax0), max(1, ay1 - ay0)
    pix = bytearray()
    for ay in range(ay0, ay1):
        row = bytearray()
        for ax in range(ax0, ax1):
            row += bytes(px(w, ch, buf, ax, ay)) * sc
        pix += row * sc
    write_png(out, aw * sc, ah * sc, bytes(pix))
    print("%s -> %s  %dx%d（逻辑区 %dx%d → 实际像素 %dx%d，截图缩放 %.4g，放大 %dx）"
          % (src, out, aw * sc, ah * sc, cw, chh, aw, ah, sc_auto, sc))


if __name__ == "__main__":
    main()
