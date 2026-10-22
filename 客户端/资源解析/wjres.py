#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
wjres.py - 《金庸群侠传》(网金) 旧版客户端资源转换器
把 share\\role、share\\pic 等目录里的 .mrg(+.pal) 转成网页可直接使用的 PNG 图集 + JSON。

用法:
  python wjres.py <输入.mrg 或 目录> [<输入2> ...] [-o 输出目录] [--variants N] [--page 4096]
                  [--no-jpeg] [--limit-records N] [--dump-chunks]
  例:
  python wjres.py ..\\..\\share\\role\\boy01.mrg -o out --variants 5
  python wjres.py ..\\..\\share\\pic -o out          (整个目录, 很慢)

依赖: Python 3.8+, Pillow (pip install pillow)

只读输入文件, 不会修改原始资源。格式说明见 ..\\资源格式说明.md
"""
import argparse, glob, json, os, re, struct, sys, time

try:
    from PIL import Image
except ImportError:
    print('需要 Pillow: pip install pillow'); sys.exit(1)

# ----------------------------------------------------------------- 基础
def rgb565_to_rgb(v):
    r = (v >> 11) & 31; g = (v >> 5) & 63; b = v & 31
    return ((r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2))

def build_rgb_table():
    return [rgb565_to_rgb(v) for v in range(65536)]
RGB = build_rgb_table()

MAGIC_LZ = b'\x56\x8d\x0f\x20'      # 压缩块头: magic + u32 解压后长度

def lzss(src, outlen=None):
    """Okumura LZSS: 4096 环形缓冲, 初始 0x20, 起点 0xFEE, 匹配长度 3..18 (loginp.exe FUN_004a7f50)"""
    ring = bytearray(b'\x20' * 4096)
    r = 0xfee
    out = bytearray()
    i = 0; n = len(src); flags = 0
    while True:
        flags >>= 1
        if not (flags & 0x100):
            if i >= n: break
            flags = src[i] | 0xff00; i += 1
        if flags & 1:
            if i >= n: break
            c = src[i]; i += 1
            out.append(c); ring[r] = c; r = (r + 1) & 0xfff
        else:
            if i + 1 >= n: break
            b1 = src[i]; b2 = src[i + 1]; i += 2
            pos = b1 | ((b2 & 0xf0) << 4)
            for k in range((b2 & 0xf) + 3):
                c = ring[(pos + k) & 0xfff]
                out.append(c); ring[r] = c; r = (r + 1) & 0xfff
        if outlen is not None and len(out) >= outlen: break
    return bytes(out)

def lz_chunk(rec):
    """带 568D0F20 头的压缩块 -> 解压数据, 否则 None"""
    if rec[:4] == MAGIC_LZ and len(rec) >= 8:
        L = struct.unpack_from('<I', rec, 4)[0]
        return lzss(rec[8:], L)
    return None

# ----------------------------------------------------------------- .mrg 容器
class Mrg:
    """<u32 count><u32 namesLen> count*{<u32 size><u32 offset><u32 0><u8 type>} names(CRLF) data"""
    def __init__(self, path):
        self.path = path
        self.data = open(path, 'rb').read()
        d = self.data
        if len(d) < 8:
            self.count = 0; self.recs = []; self.names = []; self.base = 8; return
        self.count, nl = struct.unpack_from('<II', d, 0)
        p = 8
        if p + 13 * self.count + nl > len(d):
            raise ValueError('不是 mrg 容器: %s' % path)
        self.recs = []
        for i in range(self.count):
            sz, off, hi, t = struct.unpack_from('<IIIB', d, p); p += 13
            self.recs.append((sz, off, t))
        self.names = d[p:p + nl].decode('gbk', 'replace').split('\r\n')
        self.base = p + nl
        # 名字表按 CRLF 结尾, 末尾多一个空串
        while len(self.names) < self.count: self.names.append('')

    def get(self, i):
        sz, off, t = self.recs[i]
        a = self.base + off
        return self.data[a:a + sz]

# ----------------------------------------------------------------- 各类记录解码
def parse_rle6(rec):
    if len(rec) < 24: return None
    w, h, cw, ch, p = struct.unpack_from('<5I', rec, 0)
    if p % 2 or p > 512 or w == 0 or h == 0 or w > 65535 or h > 65535 or w * h > 200000000: return None
    if 24 + p > len(rec): return None
    pal = list(struct.unpack_from('<%dH' % (p // 2), rec, 20))
    s = struct.unpack_from('<I', rec, 20 + p)[0]
    return w, h, cw, ch, pal, s, rec[24 + p:]

def decode_rle6(rec):
    """-> (w,h,cw,ch,索引字节(w*h),pal) 失败抛 ValueError"""
    t = parse_rle6(rec)
    if not t: raise ValueError('hdr')
    w, h, cw, ch, pal, s, data = t
    if s != len(data): raise ValueError('size')
    out = bytearray(); i = 0; n = len(data)
    for y in range(h):
        x = 0
        while x < w:
            if i >= n: raise ValueError('eof')
            c = data[i]
            if c == 0:                       # 0: 本行剩余像素全部是字面量
                k = w - x
                if i + 1 + k > n: raise ValueError('eof lit')
                out += data[i + 1:i + 1 + k]; i += 1 + k; x = w
            else:                            # (count, index) 游程
                if i + 1 >= n: raise ValueError('eof run')
                out += data[i + 1:i + 2] * c; i += 2; x += c
        if x != w: raise ValueError('row overrun')
    if i != n: raise ValueError('trailing')
    return w, h, cw, ch, bytes(out), pal

def parse_cp(r):
    """.cp: <u32 n><256*u16 调色板><n*12 帧表{i16 x,i16 y,u16 w,u16 h,u32 累计末偏移}><LZSS 帧数据...>"""
    if len(r) < 516: return None
    n = struct.unpack_from('<I', r, 0)[0]
    if not (0 < n < 5000) or 516 + 12 * n > len(r): return None
    pal = struct.unpack_from('<256H', r, 4)
    ents = [struct.unpack_from('<hhHHI', r, 516 + 12 * i) for i in range(n)]
    ds = 516 + 12 * n
    total = max(e[4] for e in ents)          # 末偏移是累计值; 未用帧为全 0
    if ds + total != len(r): return None
    frames = []; prev = 0
    for (x, y, w, h, end) in ents:
        if end < prev: end = prev
        frames.append((x, y, w, h, r[ds + prev:ds + end])); prev = end
    return pal, frames

def idx_to_rgba(idx, w, h, pal, colorkey=True, alpha=255):
    """调色板索引 -> RGBA. 颜色 0x0000 当作透明色键(游戏用 0 色键)。"""
    npal = len(pal)
    tab = [(0, 0, 0, 0)] * 256
    for i in range(256):
        v = pal[i] if i < npal else 0
        if colorkey and v == 0: tab[i] = (0, 0, 0, 0)
        else:
            rgb = RGB[v]; tab[i] = (rgb[0], rgb[1], rgb[2], alpha)
    buf = bytearray(w * h * 4)
    j = 0
    for v in idx:
        buf[j:j + 4] = bytes(tab[v]); j += 4
    return Image.frombytes('RGBA', (w, h), bytes(buf))

def raw565_to_rgba(px, w, h, colorkey=True):
    vals = struct.unpack('<%dH' % (w * h), px)
    buf = bytearray(w * h * 4); j = 0
    for v in vals:
        if colorkey and v == 0: buf[j:j + 4] = b'\0\0\0\0'
        else:
            r, g, b = RGB[v]; buf[j] = r; buf[j + 1] = g; buf[j + 2] = b; buf[j + 3] = 255
        j += 4
    return Image.frombytes('RGBA', (w, h), bytes(buf))

def try_raw565(rec):
    """两种头: <w><h> + 2wh 字节 ; <w><h><size=2wh> + 数据. 返回 (w,h,pixelbytes) 或 None"""
    if len(rec) >= 8:
        w, h = struct.unpack_from('<II', rec, 0)
        if 0 < w < 8192 and 0 < h < 8192 and len(rec) == 8 + 2 * w * h: return w, h, rec[8:]
    if len(rec) >= 12:
        w, h, s = struct.unpack_from('<III', rec, 0)
        if 0 < w < 8192 and 0 < h < 8192 and s == 2 * w * h and len(rec) == 12 + s: return w, h, rec[12:]
    return None

# ----------------------------------------------------------------- 图集打包
class Atlas:
    def __init__(self, page):
        self.page = page; self.pages = []        # list of dict(img, x, y, rowh)
        self.items = []
        self.sizes = {}                          # 保存后: 图集文件名 -> [w, h]

    def _new_page(self):
        self.pages.append({'items': [], 'x': 0, 'y': 0, 'rowh': 0, 'w': 0, 'h': 0})
        return self.pages[-1]

    def add(self, img, meta):
        w, h = img.size
        if w > self.page or h > self.page:       # 太大: 独立成图
            meta = dict(meta); meta['standalone'] = True
            self.items.append((None, img, meta)); return
        if not self.pages: self._new_page()
        pg = self.pages[-1]
        pad = 1
        if pg['x'] + w + pad > self.page:
            pg['y'] += pg['rowh'] + pad; pg['x'] = 0; pg['rowh'] = 0
        if pg['y'] + h + pad > self.page:
            pg = self._new_page()
        x, y = pg['x'], pg['y']
        pg['x'] += w + pad; pg['rowh'] = max(pg['rowh'], h)
        pg['w'] = max(pg['w'], x + w); pg['h'] = max(pg['h'], y + h)
        self.items.append((len(self.pages) - 1, img, dict(meta, x=x, y=y)))

    def save(self, outdir, prefix='atlas'):
        os.makedirs(outdir, exist_ok=True)
        imgs = []
        for pi, pg in enumerate(self.pages):
            sheet = Image.new('RGBA', (max(pg['w'], 1), max(pg['h'], 1)), (0, 0, 0, 0))
            for (p, img, meta) in self.items:
                if p == pi: sheet.paste(img, (meta['x'], meta['y']))
            sheet.save(os.path.join(outdir, '%s_%d.png' % (prefix, pi)))
            self.sizes['%s_%d.png' % (prefix, pi)] = list(sheet.size)
        out = []
        sn = 0
        for (p, img, meta) in self.items:
            m = dict(meta)
            if p is None:
                fn = '%s_big%d.png' % (prefix, sn); sn += 1
                img.save(os.path.join(outdir, fn)); m['file'] = fn; self.sizes[fn] = list(img.size)
                m['page'] = fn; m['x'] = 0; m['y'] = 0       # 与普通项统一(旧字段 file/standalone 保留)
            else:
                m['page'] = '%s_%d.png' % (prefix, p)
            m['w'], m['h'] = img.size
            out.append(m)
        return out

# ----------------------------------------------------------------- 转换一个 mrg
SHADOW_RE = re.compile(r'^[a-z]\d+s\.cp\d*$', re.I)

def find_pal(mrg_path):
    stem = os.path.splitext(mrg_path)[0]
    for cand in (stem + '.pal', re.sub(r'(?<=[a-zA-Z])0+(?=\d)', '', stem) + '.pal'):
        if os.path.isfile(cand): return cand
    return None

def load_pal(path):
    """.pal: 重复的块 <u8 nameLen><name><u16*1536 = 6 套 * 256 色 RGB565>, 块长 3079. -> {name_lower: [6 套 256 色]}"""
    d = open(path, 'rb').read(); res = {}
    p = 0
    while p < len(d):
        ln = d[p]; name = d[p + 1:p + 1 + ln].decode('ascii', 'replace').lower()
        body = d[p + 1 + ln:p + 1 + ln + 3072]
        if len(body) < 3072: break
        v = struct.unpack('<1536H', body)
        res[name] = [list(v[k * 256:(k + 1) * 256]) for k in range(6)]
        p += 1 + ln + 3072
    return res

def convert_mrg(path, outroot, args):
    m = Mrg(path)
    name = os.path.splitext(os.path.basename(path))[0]
    outdir = os.path.join(outroot, name)
    atlas = Atlas(args.page)
    jpegs = []; bins = []; skipped = 0; records = []
    palpath = find_pal(path)
    pals = load_pal(palpath) if palpath else {}
    variants_atlas = {}                 # variant -> Atlas
    n = m.count if not args.limit_records else min(m.count, args.limit_records)
    stats = {}
    for i in range(n):
        sz, off, t = m.recs[i]
        rname = m.names[i]
        if sz == 0: continue
        rec = m.get(i)
        meta = {'name': rname, 'index': i, 'type': t}
        kind = None
        try:
            if rec[:2] == b'\xff\xd8':
                kind = 'jpeg'
                if not args.no_jpeg:
                    os.makedirs(os.path.join(outdir, 'jpg'), exist_ok=True)
                    fn = 'jpg/%s.jpg' % (re.sub(r'[\\/:*?"<>|]', '_', rname) or i)
                    fn = fn if fn not in jpegs else 'jpg/%s_%d.jpg' % (rname, i)
                    open(os.path.join(outdir, fn), 'wb').write(rec); jpegs.append(fn)
                    meta2 = dict(meta, kind='jpeg', file=fn); bins.append(meta2)
            elif rec[:4] == b'RIFF':
                kind = 'wav'
                os.makedirs(os.path.join(outdir, 'wav'), exist_ok=True)
                fn = 'wav/%s.wav' % (re.sub(r'[\\/:*?"<>|]', '_', rname) or i)
                open(os.path.join(outdir, fn), 'wb').write(rec); bins.append(dict(meta, kind='wav', file=fn))
            else:
                r565 = try_raw565(rec)
                if r565:
                    kind = 'raw565'
                    atlas.add(raw565_to_rgba(r565[2], r565[0], r565[1]), dict(meta, kind=kind))
                else:
                    try:
                        w, h, cw, ch, idx, pal = decode_rle6(rec)
                        kind = 'rle6'
                        atlas.add(idx_to_rgba(idx, w, h, pal), dict(meta, kind=kind, cw=cw, ch=ch))
                    except ValueError:
                        cp = parse_cp(rec)
                        if cp:
                            kind = 'cp'
                            pal, frames = cp
                            key = re.sub(r'^.*[\\/]', '', rname).split('.')[0].lower()
                            is_sh = bool(SHADOW_RE.match(re.sub(r'^.*[\\/]', '', rname)))
                            alpha = args.shadow_alpha if is_sh else 255
                            mc = re.search(r'\.cp(\d*)$', rname, re.I)
                            records.append({'name': rname, 'index': i, 'kind': 'cp', 'stem': key,
                                            'cpn': int(mc.group(1)) if mc and mc.group(1) else None,
                                            'nframes': len(frames), 'pal': key if key in pals else None,
                                            'shadow': is_sh, 'alpha': alpha})
                            for fi, (x, y, w, h, comp) in enumerate(frames):
                                if w == 0 or h == 0: continue
                                px = lzss(comp, w * h)
                                if len(px) != w * h:
                                    stats['cp_bad_frame'] = stats.get('cp_bad_frame', 0) + 1; continue
                                fm = dict(meta, kind='cp', frame=fi, ox=x, oy=y)
                                atlas.add(idx_to_rgba(px, w, h, pal, alpha=alpha), fm)
                                if key in pals:
                                    for v in range(1, min(args.variants, 5) + 1):
                                        if not any(pals[key][v]): continue    # 全 0 的空套(如 boy05.pal 的 1..5)不输出
                                        va = variants_atlas.setdefault(v, Atlas(args.page))
                                        va.add(idx_to_rgba(px, w, h, pals[key][v], alpha=alpha), fm)
                        else:
                            ch_ = lz_chunk(rec)
                            if ch_ is not None:
                                kind = 'lzchunk'
                                if args.dump_chunks:
                                    os.makedirs(os.path.join(outdir, 'chunks'), exist_ok=True)
                                    fn = 'chunks/%s.bin' % (re.sub(r'[\\/:*?"<>|]', '_', rname) or i)
                                    open(os.path.join(outdir, fn), 'wb').write(ch_)
                                    bins.append(dict(meta, kind='lzchunk', file=fn, size=len(ch_)))
                            else:
                                kind = 'unknown'
                                bins.append(dict(meta, kind='unknown', size=len(rec), head=rec[:16].hex()))
        except Exception as e:                     # 单条记录出错不影响整体
            kind = 'error'; bins.append(dict(meta, kind='error', error=str(e)[:80]))
        stats[kind] = stats.get(kind, 0) + 1
    items = atlas.save(outdir) if atlas.items else []
    variant_items = {}
    pages = dict(atlas.sizes)
    for v, va in variants_atlas.items():
        variant_items[str(v)] = va.save(outdir, 'atlas_v%d' % v)
        pages.update(va.sizes)
    meta = {'source': os.path.basename(path), 'count': m.count, 'palFile': os.path.basename(palpath) if palpath else None,
            'stats': stats, 'pages': pages, 'images': items, 'files': bins}
    if records: meta['records'] = records          # cp 记录级信息: stem/cpn/nframes/pal(调色板块名)/shadow/alpha
    if variant_items: meta['variants'] = variant_items     # 换色图集: 每套里的图项(只含有 .pal 块的记录)
    if pals:
        meta['palettes'] = {k: [[('%02x%02x%02x' % RGB[c]) for c in pal] for pal in v] for k, v in pals.items()}
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, 'atlas.json'), 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False)
    return stats

def main():
    ap = argparse.ArgumentParser(description='网金 .mrg -> PNG 图集 + JSON')
    ap.add_argument('inputs', nargs='+')
    ap.add_argument('-o', '--out', default='out')
    ap.add_argument('--variants', type=int, default=0, help='role: 额外输出 .pal 里第 1..N 套换色图集(最多5)')
    ap.add_argument('--page', type=int, default=4096)
    ap.add_argument('--no-jpeg', action='store_true')
    ap.add_argument('--limit-records', type=int, default=0)
    ap.add_argument('--dump-chunks', action='store_true', help='把 568D0F20 压缩块解压后另存 .bin')
    ap.add_argument('--shadow-alpha', type=int, default=128)
    args = ap.parse_args()
    files = []
    for inp in args.inputs:
        if os.path.isdir(inp):
            files += sorted(glob.glob(os.path.join(inp, '*.mrg')))
        else:
            files.append(inp)
    for f in files:
        t0 = time.time()
        try:
            st = convert_mrg(f, args.out, args)
            print('%-40s %6.1fs %s' % (os.path.basename(f), time.time() - t0, st))
        except Exception as e:
            print('%-40s FAIL %s' % (os.path.basename(f), e))

if __name__ == '__main__':
    main()
