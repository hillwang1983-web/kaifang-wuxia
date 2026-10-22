#!/usr/bin/env python3
"""武功动画描述：share\\dat\\KKF*.dat（键 = 技能 id，如 800301）+ share\\pic\\KongFu*.mrg（键 = 图片名，一张竖排帧序列图）。

KKF 记录格式（逆向 FUN_00985ee4，0x985ee4；调用方 FUN_00984858 以技能 id 字符串为键，在 KKF2…KKF10、KKF.dat 里依次找）：
    b0 b1 b2 b3 b4 nseg-1        6 字节头（b4 = G+0x333，b5 = 段数-1）
    每段（帧）：
        nA nB                    两个计数
        B 项 × nB（每项 77 字节）：u16 +0x46, u16 +0x48, u8 +4, name[61]（Pascal 串）, u16 +0x4a, u8 +0x4c, u32 +0x42, u32 +0
        A 项 × nA（每项 75 字节）：u16 a, u16 b, u8 c, name[51]（Pascal 串，= KongFu*.mrg 里的图片名）, u16 d, u8 e, rect[16] = x0,y0,x1,y1（u32，图上取的矩形，含右下）
    尾部：i16 速度参数（+0x331，存进对象 +0x3d8）、128 字节 +0x334（含义没解）

播放（逆向 0x9873a6 推进、0x9884cc 绘制）：
    * 帧推进：间隔 = |速度参数 − 20| × 全局动画速度(默认 10) ÷ 10 毫秒，但每次刷新最多前进一帧，所以实际 ≈ max(刷新周期, |速度−20|) 毫秒；
      速度参数最常见 15（2147 条里 1495 条），其余 1 / 10 / 20 / 33 / 50 / 66 / 100 / 200 ……
    * 绘制：A 项的 d（u16 +0x48）= 本对象图片槽位序号（第几张图），a / b（i16，+0 / +2）= 相对锚点的像素偏移；
      左上角 x = 锚点x + a − 图宽/2，y = 锚点y + b − (y1−y0)/2，然后把图上矩形 (x0,y0,x1,y1) 贴上去。即以锚点为中心。
"""
import glob
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import evtdata  # noqa: E402

SHARE = os.environ.get("JY_SHARE", os.path.normpath(os.path.join(HERE, "..", "share")))


def _pstr(b):
    n = b[0]
    return b[1:1 + n].decode("big5", "replace")


def parse_record(d):
    """-> dict(head, nseg, frames=[{A:[...], B:[...]}], tail)；格式不符时抛 ValueError。"""
    if len(d) < 6:
        raise ValueError("short")
    head = tuple(d[:5])
    nseg = d[5] + 1
    o = 6
    frames = []
    for _ in range(nseg):
        if o + 2 > len(d):
            raise ValueError("eof seg")
        na, nb = d[o], d[o + 1]
        o += 2
        B = []
        for _ in range(nb):
            if o + 77 > len(d):
                raise ValueError("eof B")
            B.append({
                "v46": struct.unpack_from("<H", d, o)[0], "v48": struct.unpack_from("<H", d, o + 2)[0],
                "v04": d[o + 4], "name": _pstr(d[o + 5:o + 66]),
                "v4a": struct.unpack_from("<H", d, o + 66)[0], "v4c": d[o + 68],
                "v42": struct.unpack_from("<I", d, o + 69)[0], "v00": struct.unpack_from("<I", d, o + 73)[0]})
            o += 77
        A = []
        for _ in range(na):
            if o + 75 > len(d):
                raise ValueError("eof A")
            A.append({
                "a": struct.unpack_from("<H", d, o)[0], "b": struct.unpack_from("<H", d, o + 2)[0], "c": d[o + 4],
                "name": _pstr(d[o + 5:o + 56]),
                "d": struct.unpack_from("<H", d, o + 56)[0], "e": d[o + 58],
                "rect": struct.unpack_from("<4I", d, o + 59)})
            o += 75
        frames.append({"A": A, "B": B})
    tail = d[o:]
    speed = struct.unpack_from("<h", tail, 0)[0] if len(tail) >= 2 else 15      # +0x331 → 对象 +0x3d8：帧速度参数
    return {"head": head, "nseg": nseg, "frames": frames, "tail": tail, "speed": speed, "size": len(d)}


_KKF = None


def kkf_index():
    """技能 id（str）-> (KKF 文件名, 记录字节)，先 KKF2…KKF10 再 KKF.dat（和原版查找顺序一致，先找到的为准）。"""
    global _KKF
    if _KKF is not None:
        return _KKF
    idx = {}
    order = [os.path.join(SHARE, "dat", "KKF%d.dat" % n) for n in range(10, 1, -1)] + [os.path.join(SHARE, "dat", "KKF.dat")]
    for f in order:
        if not os.path.isfile(f):
            continue
        m = evtdata.mrg_open(f)
        for k in m.keys():
            if k in idx:
                continue
            v = m[k]
            idx[k] = (os.path.basename(f), v[0] if isinstance(v, (tuple, list)) else v)
    _KKF = idx
    return idx


def skill_anim(skill_id):
    """技能 id -> 解析后的动画记录（没有则 None）。键重映射同 FUN_00984420。"""
    sid = int(skill_id)
    if sid < 999999:
        if 0x1b0cf < sid < 0x1b0db:
            sid = 0x1b071
        elif 0x581c3 < sid < 0x581cf:
            sid = 0x58160
        elif 0x2e823 < sid < 0x2e82f or 0x5d7b3 < sid < 0x5d7bf:
            sid = 0xc38e9
        elif 0x24e40 < sid < 0x24e43:
            sid = 0x24e43
        elif 0x50bcb < sid < 0x50bd7:
            sid = 0xc3885
    ent = kkf_index().get(str(sid))
    if not ent:
        return None
    r = parse_record(ent[1])
    r["file"], r["key"] = ent[0], str(sid)
    return r


def main():
    ids = sys.argv[1:] or ["800301"]
    for s in ids:
        r = skill_anim(s)
        if not r:
            print(s, "无动画记录")
            continue
        print("==", s, r["file"], "头", r["head"], "帧数", r["nseg"], "尾", len(r["tail"]), "字节")
        for i, f in enumerate(r["frames"]):
            print("  帧%d A=%s B=%s" % (i, [(x["name"], x["rect"], x["a"], x["b"], x["c"], x["d"], x["e"]) for x in f["A"]],
                                      [(x["name"], x["v00"], x["v42"], x["v46"], x["v48"]) for x in f["B"]]))


if __name__ == "__main__":
    main()
