"""场景可走区半自动描边：从可走区遮罩生成关卡用的地面与碰撞多边形，并出一张叠在底图上的核对图。

美术交场景底图时可以顺带交一张同尺寸的遮罩（白 = 可走，黑 = 不可走）；没交的话开发照着底图在任何画图软件里涂一张。
用法（在 原型/山寺/ 下）：
    python tools/trace_walkable.py mask <场景名> <遮罩.png> [--cell 8] [--eps 6] [--key floor]
        → 写 data/walk/<场景名>.json：floor = 最大一块可走区的外轮廓，blocks = 它里面不可走的洞（柱子、桌子……）
          --key 换成 hall 之类，就只写这一个键（如藏经阁战斗时锁住的大厅），其余键保留
    python tools/trace_walkable.py overlay <场景名> [--bg 底图.png]
        → 把 data/walk/<场景名>.json 现有的多边形画到底图上，存 UI设计/可走区核对/<场景名>.png，用眼睛核对
只依赖 Pillow。网格按 cell 像素取样（默认 8），轮廓用 Douglas–Peucker 按 eps 像素简化。
"""
import argparse
import json
import pathlib
import sys

from PIL import Image, ImageDraw

ROOT = pathlib.Path(__file__).resolve().parent.parent


def grid_from_mask(path, cell):
    img = Image.open(path).convert('L')
    w, h = img.size
    gw, gh = w // cell, h // cell
    small = img.resize((gw, gh), Image.BOX)
    px = small.load()
    return [[px[x, y] >= 128 for x in range(gw)] for y in range(gh)], gw, gh


def loops(grid, gw, gh):
    """可走格与不可走格之间的边，按「可走在左手边」定向，再串成闭合环"""
    def walk(x, y):
        return 0 <= x < gw and 0 <= y < gh and grid[y][x]
    nxt = {}
    for y in range(gh):
        for x in range(gw):
            if not grid[y][x]:
                continue
            if not walk(x, y - 1):
                nxt[(x + 1, y)] = (x, y)          # 上边，往左走
            if not walk(x, y + 1):
                nxt[(x, y + 1)] = (x + 1, y + 1)  # 下边，往右走
            if not walk(x - 1, y):
                nxt[(x, y)] = (x, y + 1)          # 左边，往下走
            if not walk(x + 1, y):
                nxt[(x + 1, y + 1)] = (x + 1, y)  # 右边，往上走
    out = []
    while nxt:
        start = next(iter(nxt))
        ring = [start]
        cur = nxt.pop(start)
        while cur != start and cur in nxt:
            ring.append(cur)
            cur = nxt.pop(cur)
        if len(ring) >= 4:
            out.append(ring)
    return out


def area(ring):
    return sum(ring[i][0] * ring[(i + 1) % len(ring)][1] - ring[(i + 1) % len(ring)][0] * ring[i][1] for i in range(len(ring))) / 2.0


def rdp(points, eps):
    if len(points) < 3:
        return points
    (x1, y1), (x2, y2) = points[0], points[-1]
    dx, dy = x2 - x1, y2 - y1
    norm = (dx * dx + dy * dy) ** 0.5 or 1.0
    best, idx = 0.0, 0
    for i in range(1, len(points) - 1):
        d = abs(dy * points[i][0] - dx * points[i][1] + x2 * y1 - y2 * x1) / norm
        if d > best:
            best, idx = d, i
    if best <= eps:
        return [points[0], points[-1]]
    return rdp(points[:idx + 1], eps)[:-1] + rdp(points[idx:], eps)


def simplify_ring(ring, eps):
    # 环先在离起点最远的地方切开，两段分别简化再接回
    far = max(range(len(ring)), key=lambda i: (ring[i][0] - ring[0][0]) ** 2 + (ring[i][1] - ring[0][1]) ** 2)
    a = rdp(ring[:far + 1], eps)
    b = rdp(ring[far:] + [ring[0]], eps)
    return a[:-1] + b[:-1]


def trace(mask, cell, eps):
    grid, gw, gh = grid_from_mask(mask, cell)
    rings = [[(x * cell, y * cell) for x, y in r] for r in loops(grid, gw, gh)]
    # 屏幕坐标 y 朝下：「可走在左手边」走出来的外轮廓面积为负，洞为正
    outer = [r for r in rings if area(r) < 0]
    holes = [r for r in rings if area(r) > 0]
    if not outer:
        sys.exit('遮罩里没有可走区（白色）')
    floor = max(outer, key=lambda r: -area(r))
    xs = [p[0] for p in floor]
    ys = [p[1] for p in floor]
    inside = [h for h in holes if min(xs) <= h[0][0] <= max(xs) and min(ys) <= h[0][1] <= max(ys)]
    floor = simplify_ring(floor, eps)
    blocks = [simplify_ring(h, eps) for h in inside if abs(area(h)) >= cell * cell * 2]
    return floor, blocks


def overlay(scene, bg, data, out):
    img = Image.open(bg).convert('RGBA') if bg else Image.new('RGBA', (1920, 1080), (40, 40, 48, 255))
    layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    colors = {'floor': (80, 220, 120, 70), 'hall': (255, 210, 74, 50)}
    for key, poly in data.items():
        if key == 'blocks':
            for b in poly:
                d.polygon([tuple(p) for p in b], fill=(220, 60, 60, 110), outline=(255, 80, 80, 255))
        elif isinstance(poly, list) and poly and isinstance(poly[0], list) and len(poly[0]) == 2:
            d.polygon([tuple(p) for p in poly], fill=colors.get(key, (80, 160, 255, 50)), outline=(255, 255, 255, 255))
    img.alpha_composite(layer)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('mode', choices=['mask', 'overlay'])
    ap.add_argument('scene')
    ap.add_argument('mask', nargs='?')
    ap.add_argument('--cell', type=int, default=8)
    ap.add_argument('--eps', type=float, default=6.0)
    ap.add_argument('--key', default='floor')
    ap.add_argument('--bg')
    a = ap.parse_args()
    path = ROOT / 'data' / 'walk' / (a.scene + '.json')
    data = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    if a.mode == 'mask':
        if not a.mask:
            sys.exit('mask 模式要给遮罩图')
        floor, blocks = trace(a.mask, a.cell, a.eps)
        data[a.key] = [list(p) for p in floor]
        if a.key == 'floor':
            data['blocks'] = [[list(p) for p in b] for b in blocks]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False) + '\n', encoding='utf-8')
        print('写入 %s：%s 外轮廓 %d 点，碰撞 %d 块' % (path.relative_to(ROOT), a.key, len(floor), len(blocks) if a.key == 'floor' else 0))
    out = overlay(a.scene, a.bg, data, ROOT / 'UI设计' / '可走区核对' / (a.scene + '.png'))
    print('核对图：%s' % out.relative_to(ROOT))


if __name__ == '__main__':
    main()
