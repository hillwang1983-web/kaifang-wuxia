#!/usr/bin/env python3
"""任务手册：share\\dat\\MyDuty.dat（"我的任务"里的任务说明）。

格式（实测）：整个文件是 69 字节的槽（262 个），每槽 = Pascal 字符串（长度 1 字节 + Big5 文字，最多 68 字节）+ 补零。
  "N.標題：說明"  门派的打工任务
  "#名字"  分类标题（主線任務 / 江湖任務 / …）
  "※标题（等级）：说明"  主线任务；"◎标题（等级）：说明"  支线任务；一行写不下就接着占下一个槽（不以符号开头的非空槽 = 上一条的续行）
  全角空格 + "回頂端"  版面占位，丢掉。
这个文件只有说明文字，**没有**"这个任务做到哪一步"的数据——原版靠服务端告知任务状态，新服务端没有任务系统，所以页面只能当"任务手册"用。
"""
import os
import re

_HERE = os.path.dirname(os.path.abspath(__file__))
DAT_DIR = os.environ.get("JY_DAT") or (os.path.join(_HERE, "share", "dat") if os.path.isdir(os.path.join(_HERE, "share", "dat")) else os.path.normpath(os.path.join(_HERE, "..", "share", "dat")))
SLOT = 69
KIND = {"※": "main", "◎": "side"}
_TITLE = re.compile(r"^(?P<title>[^（(：:]+)(?:[（(](?P<level>[^）)]*)[）)])?\s*(?:[：:](?P<desc>.*))?$", re.S)


def parse(data: bytes):
    """-> [{"name": 分类名, "entries": [{"kind","title","level","desc"}]}]"""
    cats, cur, last = [], None, None
    for i in range(len(data) // SLOT):
        s = data[i * SLOT:(i + 1) * SLOT]
        n = s[0]
        if not n or n > SLOT - 1:
            continue
        txt = s[1:1 + n].decode("big5", "replace")
        if txt.startswith("#"):
            cur = {"name": txt[1:].strip(), "entries": []}
            cats.append(cur)
            last = None
        elif txt[:1] in KIND and cur is not None:
            m = _TITLE.match(txt[1:].strip())
            last = {"kind": KIND[txt[0]], "title": (m.group("title") if m else txt[1:]).strip(), "level": (m.group("level") or "").strip() if m else "",
                    "desc": ((m.group("desc") or "") if m else "").strip()}
            cur["entries"].append(last)
        elif cur is not None and re.match(r"^\d+\.", txt):            # 门派的打工任务："1.標題：說明"
            m = _TITLE.match(re.sub(r"^\d+\.", "", txt).strip())
            last = {"kind": "job", "title": (m.group("title") if m else txt).strip(), "level": "", "desc": ((m.group("desc") or "") if m else "").strip()}
            cur["entries"].append(last)
        elif last is not None and txt.strip("　 ") and "回頂端" not in txt:
            last["desc"] += txt.strip()
        elif "回頂端" in txt:
            last = None
    for c in cats:                          # "※打工任務" 只是小标题（没有说明），丢掉
        c["entries"] = [e for e in c["entries"] if not (e["title"] == "打工任務" and not e["desc"] and not e["level"])]
    return [c for c in cats if c["entries"]]


def load(path=None):
    p = path or os.path.join(DAT_DIR, "MyDuty.dat")
    try:
        return parse(open(p, "rb").read())
    except OSError:
        return []


if __name__ == "__main__":
    for c in load():
        print("#", c["name"], len(c["entries"]))
        for e in c["entries"][:3]:
            print("   ", e)
