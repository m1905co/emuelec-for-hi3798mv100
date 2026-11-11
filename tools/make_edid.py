#!/usr/bin/env python3
"""
构造一份合法的 EDID 1.4 (128 字节) 并写入 baseparam.img 的
BASE_KEY_EDID_LENTH / BASE_KEY_EDID_CONTENT 字段。

用途：机顶盒 HDMI TX 因读不到真实 EDID（能力表全零）而把输出强制降为 720p。
灌入一份声明支持 1080p60 / 4K 的 EDID 可解除该降级。

EDID 结构（128 字节）：
  0-7    header       00 FF FF FF FF FF FF 00
  8-9    manufacturer ID (big-endian)
  10-11  product code  (little-endian)
  12-15  serial number(little-endian)
  16     week of manufacture
  17     year - 1990
  18     EDID version
  19     EDID revision
  20-24  basic display parameters
  25-34  chromaticity coordinates
  35-37  established timings
  38-53  standard timings (8 x 2 bytes)
  54-71  detailed timing descriptor #1 (HDMI 首选，含 4K/1080p 时序)
  72-125 descriptors #2-#4
  126    extension block count
  127    checksum (使 0..127 字节和 % 256 == 0)
"""
import struct, sys


def dtd(pixel_clk_khz, hactive, hblank, vsync_start, vsync_end, vactive,
        vblank_front, vblank_back, hsync_off, hsync_w, vsync_off, vsync_w,
        h_size_mm, v_size_mm, name=b"HDMI"):
    """构造 18 字节 Detailed Timing Descriptor"""
    hactive_hb = hactive + hblank
    vactive_vb = vactive + vblank_front + vblank_back

    d = bytearray(18)
    d[0] = (pixel_clk_khz // 10) & 0xFF          # pixel clock / 10 kHz, low
    d[1] = (pixel_clk_khz // 10) >> 8             # high
    d[2] = hactive & 0xFF
    d[3] = hblank & 0xFF
    d[4] = ((hactive >> 8) << 4) | (hblank >> 8)
    d[5] = vactive & 0xFF
    d[6] = (vblank_front + vblank_back) & 0xFF
    d[7] = ((vactive >> 8) << 4) | ((vblank_front + vblank_back) >> 8)
    d[8] = (hsync_off & 0xFF)
    d[9] = (hsync_w & 0xFF)
    d[10] = (((vsync_off & 0xFF) << 4) | ((vsync_w & 0xFF) >> 4))
    d[11] = (((vsync_off >> 8) & 0x0F) << 4) | ((vblank_front >> 4) & 0x0F)
    d[12] = (vsync_end & 0xFF)
    d[13] = (h_size_mm & 0xFF)
    d[14] = (v_size_mm & 0xFF)
    d[15] = 0x00
    d[16] = 0x00
    d[17] = 0x0E                                   # descriptor type + version

    # 名称/描述符：ASCII 文本，左对齐
    txt = name[:13]
    for i, ch in enumerate(txt):
        d[4 + i] = ch if 32 <= ch < 127 else 0x20
    d[4 + len(txt)] = 0x0A
    return bytes(d)


def build_edid():
    e = bytearray(128)

    # 0-7 header
    e[0:8] = bytes([0x00, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0x00])

    # 8-9 manufacturer ID: 3 个大写字母各取低 5 位，压成 16 bit 大端
    #   'H'=0x48->0x08, 'S'=0x53->0x13, 'T'=0x54->0x14
    def mfg(mid):
        n = ((ord(mid[0]) - 64) << 10) | ((ord(mid[1]) - 64) << 5) | (ord(mid[2]) - 64)
        return n

    struct.pack_into('>H', e, 8, mfg("HST"))

    # 10-11 product code (LE)
    struct.pack_into('<H', e, 10, 0x3701)

    # 12-15 serial (LE)
    struct.pack_into('<I', e, 12, 0x00000001)

    e[16] = 10      # week
    e[17] = 2026 - 1990   # year offset
    e[18] = 1       # EDID version
    e[19] = 4       # EDID revision

    # 20-24 basic display params
    # 字节20: bits7-4 = 水平尺寸/16cm, bits3-0 = 垂直尺寸/16cm
    #   160cm/16 = 10, 90cm/16 = 5  -> (10<<4)|5 = 0xA5
    e[20] = (10 << 4) | 5          # 160cm x 90cm
    e[21] = 0x00                   # gamma = 2.2 (value 0 => 2.2)
    e[22] = 0x78                   # features: digital, 8-bit, RGB 4:4:4
    # 23 feature support: 数字输入 + 8bit + RGB4:4:4
    e[23] = 0x78

    # 24-25 色度坐标低位字节 (bits7-6 = 红绿蓝白 x/y 的高 2 位)
    #   这里统一给 0x00，配合下面各坐标低 8 位构成合法 sRGB 近似值
    e[24] = 0xEE
    e[25] = 0x95

    # 26-34 色度坐标 (每组 x 低8位, y 低8位)
    e[26] = 0xA3   # red x
    e[27] = 0x54   # red y
    e[28] = 0x4C   # green x
    e[29] = 0x99   # green y
    e[30] = 0x26   # blue x
    e[31] = 0x0F   # blue y
    e[32] = 0x50   # white x
    e[33] = 0x54   # white y
    e[34] = 0x00   # 保留

    # 35-37 established timings (全部置空，不声明)
    e[35] = 0x00
    e[36] = 0x00
    e[37] = 0x00

    # 38-53 standard timings (2 bytes each, 8 slots)
    # 字节1 = (h_active-31)/2  [范围 256..2288]
    # 字节2 = bits7-6 宽高比, bits5-0 垂直刷新率-60
    # 注意：标准时序的垂直刷新率字段只能表示 60..123Hz，
    #       且水平上限为 (0xFF*2+31)=541 —— 所以 4K/1440p 无法用
    #       标准时序表达，必须走 DTD。这里只放合法的 1080p/720p/900p。
    def std(h, v, refresh=60):
        if (h, v) == (0, 0):
            return 0x01, 0x01
        if h > 541 or v > 1080:
            return 0x01, 0x01          # 超范围，标记为未使用
        ar = 0x00                       # 0=16:10, 1=4:3, 2=5:4, 3=16:9
        if h * 9 == v * 16:
            ar = 3
        elif h * 3 == v * 4:
            ar = 1
        r = refresh - 60
        if not (0 <= r <= 63):
            return 0x01, 0x01
        return ((h - 31) // 2) & 0xFF, ((ar & 0x3) << 6) | (r & 0x3F)

    st = [
        (1920, 1080, 60),   # slot 0 - 1080p60
        (1280, 720, 60),    # slot 1 - 720p60
        (1920, 1080, 50),   # slot 2 - 非法刷新(50<60) -> 会被标未使用
        (1366, 768, 60),    # slot 3
        (1280, 800, 60),    # slot 4
        (1280, 1024, 60),   # slot 5
        (1440, 900, 60),    # slot 6
        (1680, 1050, 60),   # slot 7
    ]
    for i, (h, v, r) in enumerate(st):
        a, b = std(h, v, r)
        e[38 + i * 2] = a
        e[39 + i * 2] = b

    # 54-71: detailed timing #1 -> 3840x2160@60 (4K60, HDMI 主时序)
    d4k60 = dtd(
        pixel_clk_khz=594000,
        hactive=3840, hblank=560,
        vsync_start=48, vsync_end=48, vactive=2160,
        vblank_front=8, vblank_back=32,
        hsync_off=112, hsync_w=48,
        vsync_off=8, vsync_w=12,
        h_size_mm=160, v_size_mm=90,
        name=b"4K60",
    )
    e[54:72] = d4k60

    # 72-89: detailed timing #2 -> 1920x1080@60 (含 HDMI VIC 16 / CTA-861 扩展标志)
    d1080 = dtd(
        pixel_clk_khz=148500,
        hactive=1920, hblank=280,
        vsync_start=4, vsync_end=4, vactive=1080,
        vblank_front=3, vblank_back=10,
        hsync_off=88, hsync_w=44,
        vsync_off=3, vsync_w=5,
        h_size_mm=160, v_size_mm=90,
        name=b"1080p60",
    )
    e[72:90] = d1080

    # 90-107: descriptor #3 -> 1280x720@60
    d720 = dtd(
        pixel_clk_khz=74250,
        hactive=1280, hblank=440,
        vsync_start=5, vsync_end=5, vactive=720,
        vblank_front=3, vblank_back=5,
        hsync_off=110, hsync_w=40,
        vsync_off=3, vsync_w=5,
        h_size_mm=160, v_size_mm=90,
        name=b"720p60",
    )
    e[90:108] = d720

    # 108-125: descriptor #4 -> dummy monitor name
    e[108:126] = dtd(
        pixel_clk_khz=2517, hactive=640, hblank=160,
        vsync_start=3, vsync_end=3, vactive=480,
        vblank_front=6, vblank_back=6,
        hsync_off=16, hsync_w=96,
        vsync_off=0, vsync_w=3,
        h_size_mm=160, v_size_mm=90,
        name=b"BigfishTV",
    )

    e[126] = 0   # 无扩展块

    # 127 checksum
    e[127] = (256 - (sum(e[:127]) % 256)) & 0xFF
    return bytes(e)


def main():
    src, dst = sys.argv[1], sys.argv[2]
    edid = build_edid()

    print("生成的 EDID (%d 字节):" % len(edid))
    print("  header :", edid[:8].hex())
    print("  mfg    : %s%s%s" % (chr(edid[8]), chr(edid[9]), chr(edid[8 + 1])))
    print("  ver/rev: %d.%d" % (edid[18], edid[19]))
    print("  4K60 DTD:", edid[54:60].hex())
    print("  1080 DTD:", edid[72:78].hex())
    print("  checksum: 0x%02X (sum%%256=%d)" % (edid[127], sum(edid) % 256))
    assert sum(edid) % 256 == 0, "EDID checksum 校验失败"
    print("  [OK] checksum 校验通过")

    with open(src, 'rb') as f:
        img = bytearray(f.read())
    if len(img) < 0x2000:
        raise SystemExit("输入文件太小，不是 baseparam 镜像")

    eh = img.find(b'BASE_KEY_EDID_LENTH\x00')
    ec = img.find(b'BASE_KEY_EDID_CONTENT\x00')
    if eh < 0 or ec < 0:
        raise SystemExit("未在镜像中找到 EDID 字段")

    def val(off):
        return struct.unpack_from('<I', img, off + 32)[0]

    old_len, old_buf = val(eh), val(ec)
    print("\n原镜像 @0x%X: EDID_LENTH=%d  EDID_CONTENT(buf)=%d" % (eh, old_len, old_buf))
    print("原 EDID 数据首 16 字节:", img[ec + 40:ec + 56].hex())

    if old_buf < len(edid):
        raise SystemExit("EDID 缓冲区(%d) 小于所需(%d)，无法写入" % (old_buf, len(edid)))

    # 写入长度字段
    struct.pack_into('<I', img, eh + 32, len(edid))
    # 写入 EDID 内容（缓冲区起点 = 键名 + 32 + 值4 + 保留4）
    data_off = ec + 40
    img[data_off:data_off + len(edid)] = edid
    # 清零剩余缓冲区，避免残留旧数据干扰
    for i in range(data_off + len(edid), data_off + old_buf):
        img[i] = 0

    print("新 EDID 写入后 @0x%X: EDID_LENTH=%d" % (eh, struct.unpack_from('<I', img, eh + 32)[0]))
    print("新 EDID 数据首 16 字节:", img[data_off:data_off + 16].hex())

    with open(dst, 'wb') as f:
        f.write(img)
    print("\n已写出:", dst)

    # 顺带把 baseparam.img（原刷机包里的）也处理一份，便于后续打包
    fw = 'fw/baseparam.img'
    try:
        with open(fw, 'rb') as f:
            img2 = bytearray(f.read())
        if img2.find(b'BASE_KEY_EDID_LENTH\x00') >= 0:
            struct.pack_into('<I', img2, eh + 32, len(edid))
            ec2 = img2.find(b'BASE_KEY_EDID_CONTENT\x00')
            img2[ec2 + 40:ec2 + 40 + len(edid)] = edid
            for i in range(ec2 + 40 + len(edid), ec2 + 40 + old_buf):
                img2[i] = 0
            with open('fw/baseparam_patched.img', 'wb') as f:
                f.write(img2)
            print("已写出: fw/baseparam_patched.img")
    except FileNotFoundError:
        pass


if __name__ == '__main__':
    main()