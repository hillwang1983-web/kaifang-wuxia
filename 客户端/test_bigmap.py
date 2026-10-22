#!/usr/bin/env python3
"""大地图（pic\\MapMrg*.Mrg）渲染：格子数据布局 / 贴图 / 过渡 / 切片 / 合成碰撞。用原版 share\\pic；找不到文件或没有 numpy / Pillow 就跳过。"""
import io
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

RES = []


def check(c, msg):
    RES.append(bool(c))
    print(("PASS" if c else "FAIL"), msg)


def main():
    try:
        import numpy as np
        from PIL import Image
        import bigmap
    except ImportError as e:
        print("SKIP 缺依赖：%s" % e)
        return 0
    here = os.path.dirname(os.path.abspath(__file__))
    pic = os.path.join(here, "share", "pic") if os.path.isdir(os.path.join(here, "share", "pic")) else os.path.join(here, "..", "share", "pic")
    if not os.path.exists(os.path.join(pic, "Pan_Com.mrg")):
        print("SKIP 找不到 Pan_Com.mrg")
        return 0
    bm = bigmap.BigMaps(pic)

    check(bm.has(5000) and not bm.has(1), "5000 是大地图，1 不是")
    g = bm.grid(5000)
    check(g is not None and (g[0], g[1]) == (267, 200) and g[2].shape == (200, 267, 5), "5000 = 267 × 200 格，数组 (高, 宽, 5)")
    check(bm.size(5000) == (267 * 48, 200 * 48), "像素大小 = 格数 × 48（12816 × 9600）")
    check(bm.grid(999999) is None and bm.size(999999) is None and bm.tile_jpeg(999999, 0, 0) is None, "不存在的图返回 None")

    # 地面类型都在 F 表里（没有的话画不出来）
    types = {int(t) for t in np.unique(g[2][:, :, 0])}
    check(len(types) > 5 and len(types - set(bigmap.F)) <= 2, "5000 的地面类型基本都认得（%d 种，未知 %s）" % (len(types), sorted(types - set(bigmap.F))))

    # 列优先：横向相邻格比纵向相邻格更常相同的反面——转置对了，相邻格同类型的比例应该很高
    a = g[2][:, :, 0]
    same = ((a[:, 1:] == a[:, :-1]).mean() + (a[1:, :] == a[:-1, :]).mean()) / 2
    check(same > 0.7, "相邻格同类型比例 %.2f（转置对了才会高）" % same)

    # 贴图 / 遮罩
    tex = bm._textures()
    check(len(tex) >= 30 and all(v.shape[2] == 3 and v.shape[0] % 48 == 0 for v in tex.values()), "贴图 %d 张，都是 RGB、高是 48 的倍数" % len(tex))
    masks = bm._masks()
    check(masks.shape == (8, 15, 48, 48) and masks.dtype == bool and 0 < masks.mean() < 1, "过渡遮罩 8 行 × 15 列 × 48 × 48")

    # 切片：JPEG、尺寸、不是黑的
    t = bm.tile_jpeg(5000, 13, 3)
    im = Image.open(io.BytesIO(t))
    check(im.size == (768, 768), "切片 13_3 是 768 × 768")
    check(np.asarray(im).mean() > 30, "切片 13_3 不是黑的（线程竞争修过的那块）")
    edge = Image.open(io.BytesIO(bm.tile_jpeg(5000, 16, 12)))
    check(edge.size == (12816 - 16 * 768, 9600 - 12 * 768), "边上的切片更小（%s）" % (edge.size,))
    check(bm.tile_jpeg(5000, 17, 0) is None and bm.tile_jpeg(5000, 0, 13) is None, "超出地图的切片返回 None")

    # 多线程同时渲染（网关用线程池）：新实例上并发取不同切片，都不能是黑的
    fresh = bigmap.BigMaps(pic)
    out, errs = {}, []

    def work(i):
        try:
            out[i] = np.asarray(Image.open(io.BytesIO(fresh.tile_jpeg(5000, 11 + i % 5, 1 + i // 5)))).mean()
        except Exception as e:  # noqa: BLE001
            errs.append(e)
    ths = [threading.Thread(target=work, args=(i,)) for i in range(15)]
    [x.start() for x in ths]
    [x.join() for x in ths]
    check(not errs and len(out) == 15 and min(out.values()) > 20, "15 个线程同时渲染切片：无异常、没有黑块（最暗 %.0f）" % (min(out.values()) if out else -1))

    # 碰撞：原版位图（物件节后面，0x927eb0 的布局），一小格 16 像素
    wk = bm.walk_grid(5000)
    check(wk["w"] == 12816 and wk["h"] == 9600 and wk["cell"] == 16 and wk["rows"] == 600 and wk["cols"] == 801 and wk["stride"] == 101, "碰撞格头部：801 × 600 个 16 像素小格")

    def blocked(cx, cy):
        return bool(wk["data"][cy * wk["stride"] + cx // 8] >> (cx % 8) & 1)
    col = bm.collision(5000)
    check(all(blocked(x, y) == bool(col[y, x]) for y in range(0, 600, 37) for x in range(0, 801, 29)), "打包后的碰撞格和 collision() 一致")
    water = np.argwhere(np.isin(a, bm.BLOCKED))
    wb = np.mean([col[y * 3 + 1, x * 3 + 1] for y, x in water])
    check(wb > 0.85 and wb < 1.0, "水格中心 %.0f%% 挡（剩下的是桥）" % (wb * 100))
    check(0.2 < col.mean() < 0.4, "5000 图 %.0f%% 的小格挡（山 / 林 / 水 / 城）" % (col.mean() * 100))
    check(not bm.collision(8000)[(117 * 48 + 24) // 16, (180 * 48 + 24) // 16], "8000 图新手指導員小苓站的地方能走")
    check(bm.collision(9501).shape == (90, 90), "9501（30 × 30 格）碰撞 90 × 90")
    check(bm.walk_grid(5000) is wk, "碰撞格有缓存")

    # 物件层（格子数据后面的 3 节 精灵号 / x / y）
    objs = bm.objects(5000)
    check(len(objs) > 1000 and objs == sorted(objs, key=lambda o: (o[0], o[3], o[2])), "5000 物件 %d 个（资源里有贴图的），按 节 / y / x 排好" % len(objs))
    check({o[0] for o in objs} == {0, 1, 2}, "三节都有")
    spr = bm.sprites()
    check(spr.get(10) is not None and spr.get(10).shape == (503, 512, 4), "精灵 10 = ScenePic『010』（512 × 503 的树）")
    check(spr.get(3394) is not None and spr.get(3394).shape[:2] == (144, 336), "精灵 3394 = Pan_Com（336 × 144）")
    check(spr.get(410) is not None and spr.get(410).shape[:2] == (186, 48), "精灵 410 = KcomMrg『t00410』（石碑），不是 FlashPic 的武功特效")
    check(spr.get(1010) is None, "精灵 1010 找不到（smlanti 的『T1010x』是漫画头像，不算）")
    a = np.asarray(bm.render(5000, 9600, 2304, 768, 768))
    b = np.asarray(bm.render(5000, 9600, 2304, 768, 768, objects=False))
    check((a != b).any(axis=2).mean() > 0.3, "城外那块（12_3）画上物件后有 %.0f%% 的像素变了" % ((a != b).any(axis=2).mean() * 100))
    occ = bm.occluders(5000)
    check(occ and all(set(o) == {"n", "x", "y", "w", "h", "d", "u"} and o["u"] == "/bigobj/%d.png" % o["n"] and o["y"] < o["d"] <= o["y"] + o["h"] for o in occ),
          "遮挡物件 %d 个，格式同城市图 /objects" % len(occ))
    png = bm.sprite_png(occ[0]["n"])
    check(png and png[:8] == b"\x89PNG\r\n\x1a\n" and Image.open(io.BytesIO(png)).mode == "RGBA" and bm.sprite_png(1010) is None, "精灵 PNG（透明背景）；没有的返回 None")

    # 缩略图
    ov = Image.open(io.BytesIO(bm.overview_png(5000, 2)))
    check(ov.size == (534, 400), "缩略图 = 格数 × 2")

    print("\n%d / %d 通过" % (sum(RES), len(RES)))
    return 0 if all(RES) else 1


if __name__ == "__main__":
    sys.exit(main())
