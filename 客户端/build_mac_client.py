#!/usr/bin/env python3
"""把网页客户端（网关 + 页面 + 运行需要的资源）打成 macOS 部署包 zip（UTF-8 文件名，.sh 带可执行位，只用相对路径）。

    python build_mac_client.py                 # 完整包：含全部地图背景（约 312MB 的 SceneBG*.mrg）
    python build_mac_client.py --maps none     # 不带地图（页面里地图区显示"没有找到背景图"，其它功能照常），包只有几十 MB
    python build_mac_client.py --out D:\\x      # 输出目录，默认 逆向工具\\dist
    python build_mac_client.py --update        # 增量包：只放和上一个完整包相比改过 / 新增的文件（通常几百 KB），解压覆盖到 Mac 上的 jyclient-mac/ 即可
    python build_mac_client.py --update dist\\jyclient-mac-20261022-1105.zip   # 指定对比的底包（Mac 上装的是哪个就填哪个，也可以填 .manifest.json）

每次打包都在 zip 旁边写一个 <包名>.manifest.json（包内路径 -> 大小 + sha1），增量包靠它比较；老包没有 manifest 时从 zip 里现算一次并存下。
增量包里有 更新说明.txt（底包名、改了哪些、底包里有但现在不要的文件）。

包里有（目录名 jyclient-mac/）：
  gateway.py jyclient.py packet_proxy.py parse_0x1e.py npcdata.py evtdata.py evtengine.py jyfight.py combat_server.py   运行时只用标准库，不需要 Pillow
  web/                                                    页面 + 预生成的人物精灵（model 1 的全部层 x 调色板套）+ roles.json
  web/objects/*.png                                       前景物件贴图（建筑 / 树的抠图，用来遮住走到它们后面的人；--maps none 时没有）
  data/                                                   装备数据.csv 药品.csv 商人.csv 武学系数.csv 师傅.csv（物品名 / 商人表 / 武功名 / 师傅表）+ s2t.json（简繁表）
  share/dat/Item3.Dat                                     装备外观表（外观码）\n  share/dat/Npc.Dat Npc1.Dat Npc3.Dat                     型号 -> NPC / 怪物精灵号（npcdat.py）；web/sprites/npc/ = 预生成的 NPC / 怪物精灵图集（站立 + 攻击）
  share/dat/WSG*.dat                                      地图碰撞格（建筑 / 地形挡住的格子，页面据此寻路）
  share/pic/SceneBG*.mrg                                  地图背景（--maps none 时没有）
  start_client.sh  部署说明.md  客户端库说明.md  战斗协议_客户端侧.md  test_gateway.py  client_scenario.py
不带：loginp.exe / 登录器 / 任何服务端文件 / 账号记录 / 日志 / 缓存。
"""
import argparse
import glob
import hashlib
import json
import os
import sys
import time
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
CLIENT = os.path.normpath(os.path.join(HERE, ".."))                       # 客户端目录（share、maina 在这里）
SERVER_DATA = r"C:\游戏\网金最原始文件\网金最原始文件\服务端\data"
S2T = r"C:\游戏\网金复刻\data\s2t.json"
DEPLOY = os.path.join(HERE, "deploy_mac")
ROOT = "jyclient-mac"
EXECUTABLE = {"start_client.sh"}

PY_FILES = ["gateway.py", "jyclient.py", "packet_proxy.py", "parse_0x1e.py", "npcdata.py", "npcdat.py", "dutydata.py", "evtdata.py", "evtengine.py", "jyfight.py", "notices.py", "test_notices.py", "biaoju.py", "test_biaoju.py", "client_biaoju_test.py", "lifeskill.py", "test_lifeskill.py", "client_lifeskill_test.py", "client_farm_test.py", "masters.py", "guide.py", "test_guide.py", "test_zones.py", "bigmap.py", "test_bigmap.py", "test_room.py","books.py", "test_books.py", "client_book_test.py", "test_masters.py", "client_study_test.py", "kkfdata.py", "build_fx.py", "test_kkf.py", "test_evtcond.py", "combat_server.py", "test_evt.py", "api_map.py", "test_gateway.py", "client_scenario.py"]
DOCS = ["客户端库说明.md", "客户端功能清单.md", "遗留问题.md", "C2S_0x31命令表.md", "战斗协议_客户端侧.md", "地图遇怪_接口约定.md"]
DATA_FILES = ["装备数据.csv", "药品.csv", "商人.csv", "武学系数.csv", "师傅.csv", "MOB数据.csv", "标记.csv"]


def content(src, arc):
    data = open(src, "rb").read()
    if arc.endswith(".sh"):
        data = data.replace(b"\r\n", b"\n")      # Mac 上 CRLF 的脚本跑不起来
    return data


def digest(data):
    return [len(data), hashlib.sha1(data).hexdigest()]


def manifest_of(path):
    """底包的 {包内路径: [大小, sha1]}：.manifest.json 直接读；zip 先找旁边的 manifest，没有就从 zip 里现算并存下"""
    if path.endswith(".json"):
        return json.load(open(path, encoding="utf-8"))
    mf = path + ".manifest.json"
    if os.path.isfile(mf):
        return json.load(open(mf, encoding="utf-8"))
    print("底包没有 manifest，从 zip 里算一次（只这一次慢）：", os.path.basename(path))
    out = {}
    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            if info.is_dir() or not info.filename.startswith(ROOT + "/"):
                continue
            out[info.filename[len(ROOT) + 1:]] = digest(zf.read(info))
    json.dump(out, open(mf, "w", encoding="utf-8"), ensure_ascii=False)
    return out


def latest_full(out_dir):
    zips = [z for z in glob.glob(os.path.join(out_dir, "jyclient-mac-*.zip")) if "-update-" not in os.path.basename(z) and "-nomaps" not in os.path.basename(z)]
    return max(zips, key=os.path.basename) if zips else None


def add(zf, src, arc, data=None):
    if data is None:
        data = content(src, arc)
    info = zipfile.ZipInfo(ROOT + "/" + arc, date_time=time.localtime(os.path.getmtime(src))[:6])
    info.compress_type = zipfile.ZIP_STORED if arc.lower().endswith((".png", ".jpg", ".mrg")) and len(data) > 1_000_000 else zipfile.ZIP_DEFLATED
    info.create_system = 3                        # Unix，external_attr 里的权限位才会被 Mac 的解压工具认
    mode = 0o755 if os.path.basename(arc) in EXECUTABLE else 0o644
    info.external_attr = (0o100000 | mode) << 16
    zf.writestr(info, data)
    return len(data)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=os.path.join(HERE, "dist"))
    ap.add_argument("--maps", choices=("all", "none"), default="all")
    ap.add_argument("--update", nargs="?", const="latest", default=None, metavar="底包",
                    help="打增量包；不写底包 = dist 里最新的完整包")
    a = ap.parse_args()
    items = []                                     # (源文件, 包内路径)
    for f in PY_FILES + DOCS:
        items.append((os.path.join(HERE, f), f))
    for f in os.listdir(os.path.join(HERE, "web")):
        p = os.path.join(HERE, "web", f)
        if os.path.isfile(p):
            items.append((p, "web/" + f))
    sprites = os.path.join(HERE, "web", "sprites")
    for root, _, fs in os.walk(sprites):
        for f in sorted(fs):
            if f.endswith((".png", ".json")):
                p = os.path.join(root, f)
                items.append((p, "web/sprites/" + os.path.relpath(p, sprites).replace("\\", "/")))
    if a.maps == "all":                                     # 前景物件贴图（约 115MB，没有地图背景时用不上）
        objdir = os.path.join(HERE, "web", "objects")
        if os.path.isdir(objdir):
            for f in sorted(os.listdir(objdir)):
                if f.endswith(".png"):
                    items.append((os.path.join(objdir, f), "web/objects/" + f))
        else:
            print("提示：web/objects 不存在，包里没有遮挡贴图（先 python build_objects.py --all）")
    for f in DATA_FILES:
        items.append((os.path.join(SERVER_DATA, f), "data/" + f))
    items.append((S2T, "data/s2t.json"))
    items.append((os.path.join(CLIENT, "share", "dat", "Item3.Dat"), "share/dat/Item3.Dat"))
    items.append((os.path.join(CLIENT, "maina", "MAP.csv"), "data/MAP.csv"))             # 导航页的『地点』（guide.py）
    for f in ("Npc.Dat", "Npc1.Dat", "Npc3.Dat", "MyDuty.dat", "cityportals.dat", "cityportals_kind.dat", "newbie.dat"):                  # 型号 -> NPC / 怪物精灵号（npcdat.py）
        items.append((os.path.join(CLIENT, "share", "dat", f), "share/dat/" + f))
    datdir = os.path.join(CLIENT, "share", "dat")
    for f in sorted(os.listdir(datdir)):                      # 地图碰撞格（WSG*.dat，约 18MB）
        if f.lower().startswith("wsg") and f.lower().endswith(".dat"):
            items.append((os.path.join(datdir, f), "share/dat/" + f))
    pic = os.path.join(CLIENT, "share", "pic")
    for f in sorted(os.listdir(pic)):                         # NPC 摆放 + 事件脚本 + 对话文本（NpcMrg / EvtMrg / TextMrg *.mrg，约 15MB）
        if f.lower().startswith(("npcmrg", "evtmrg", "textmrg")) and f.lower().endswith(".mrg") and os.path.getsize(os.path.join(pic, f)) > 100:
            items.append((os.path.join(pic, f), "share/pic/" + f))
    for f in sorted(os.listdir(pic)):                         # 大地图（bigmap.py）：地块 MapMrg*.Mrg + 地面贴图 Pan_J*.mrg + 过渡遮罩 / 物件精灵 Pan_Com*.mrg + ScenePic.mrg + KcomMrg*.mrg
        if f.lower().endswith(".mrg") and f.lower().startswith(("mapmrg", "pan_j", "pan_com", "scenepic", "kcommrg")):
            items.append((os.path.join(pic, f), "share/pic/" + f))
    if a.maps == "all":
        for f in sorted(os.listdir(pic)):
            if f.lower().startswith("scenebg") and f.lower().endswith(".mrg"):
                items.append((os.path.join(pic, f), "share/pic/" + f))
    items.append((os.path.join(DEPLOY, "start_client.sh"), "start_client.sh"))
    items.append((os.path.join(DEPLOY, "部署说明.md"), "部署说明.md"))
    missing = [s for s, _ in items if not os.path.isfile(s)]
    if missing:
        print("缺少文件：", *missing, sep="\n  ")
        return 1
    if not any(arc == "web/sprites/roles.json" for _, arc in items):
        print("web/sprites/roles.json 不存在：先运行 python build_sprites.py --model 1 --all")
        return 1
    os.makedirs(a.out, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M")
    if a.update:
        base = latest_full(a.out) if a.update == "latest" else a.update
        if not base or not os.path.isfile(base):
            print("找不到底包（先打一个完整包，或用 --update <zip / manifest> 指定）")
            return 1
        old = manifest_of(base)
        now, changed = {}, []
        for src, arc in items:
            data = content(src, arc)
            now[arc] = digest(data)
            if old.get(arc) != now[arc]:
                changed.append((src, arc, data))
        gone = sorted(set(old) - set(now))
        name = os.path.join(a.out, "jyclient-mac-update-%s.zip" % stamp)
        note = ["增量包：解压后把 jyclient-mac/ 覆盖到 Mac 上已有的 jyclient-mac/（同名文件替换），然后重启 start_client.sh。",
                "底包：%s" % os.path.basename(base), "", "改过 / 新增（%d 个）：" % len(changed)] + ["  " + arc for _, arc, _ in changed]
        if gone:
            note += ["", "底包里有、现在不要的（可以删，不删也不影响）："] + ["  " + g for g in gone]
        total = 0
        with zipfile.ZipFile(name, "w") as zf:
            for src, arc, data in changed:
                total += add(zf, src, arc, data)
            info = zipfile.ZipInfo(ROOT + "/更新说明.txt", date_time=time.localtime()[:6])
            info.compress_type, info.create_system, info.external_attr = zipfile.ZIP_DEFLATED, 3, (0o100644) << 16
            zf.writestr(info, "\n".join(note) + "\n")
        # 增量包装上之后，Mac 上的内容 = 这次的完整清单：存下来，下一次增量就以它为底
        json.dump(now, open(name + ".manifest.json", "w", encoding="utf-8"), ensure_ascii=False)
        print("%s\n  底包 %s；%d 个文件改过 / 新增，%d 个不再需要；原始 %.2f MB，zip %.2f MB" % (
            name, os.path.basename(base), len(changed), len(gone), total / 1e6, os.path.getsize(name) / 1e6))
        for _, arc, _ in changed[:30]:
            print("   ", arc)
        return 0
    name = os.path.join(a.out, "jyclient-mac-%s%s.zip" % (stamp, "" if a.maps == "all" else "-nomaps"))
    total = 0
    man = {}
    with zipfile.ZipFile(name, "w") as zf:
        for src, arc in items:
            data = content(src, arc)
            man[arc] = digest(data)
            total += add(zf, src, arc, data)
    json.dump(man, open(name + ".manifest.json", "w", encoding="utf-8"), ensure_ascii=False)
    print("%s\n  %d 个文件，原始 %.1f MB，zip %.1f MB" % (name, len(items), total / 1e6, os.path.getsize(name) / 1e6))
    return 0


if __name__ == "__main__":
    sys.exit(main())
