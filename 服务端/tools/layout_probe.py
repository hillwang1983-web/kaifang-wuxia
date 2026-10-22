"""差分法拆登录数据包的字段布局。

原版服务端每次 C2S 0x19 都会重新读数据库再拼 S2C 登录序列（含 0x1E 大包）。所以：
  1. 克隆一个临时角色（新 jyid，不碰现有角色）；
  2. 每次只改克隆角色的一列，重新登录，对比整条登录序列里哪些字节变了；
  3. 还原这一列。
由此得到「数据库列 → (哪个 S2C 帧, 偏移, 字节数, 字节序)」。

    python tools/layout_probe.py clone    --src 8617293 --dst 9999001
    python tools/layout_probe.py baseline --dst 9999001
    python tools/layout_probe.py probe    --dst 9999001 --table renwu --out data/layout/renwu.json
    python tools/layout_probe.py cleanup  --dst 9999001

只连本机原版服务端（默认 127.0.0.1:6731）。克隆行在 cleanup 时删除；原有角色不会被修改。
"""

from __future__ import annotations

import argparse
import json
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jyserver.codec import KEY_C2S_HANDSHAKE, FrameReader, c2s_key, encode_c2s  # noqa: E402

MYSQL = r"C:\游戏\网金最原始文件\网金最原始文件\服务端\MySQL5.5\bin\mysql.exe"
DB = "jydata"
UNKNOWN_CONST = 0x0005FCF7
CLONE_TABLES = ["renwu", "account", "char_equip", "jineng", "item", "ypsx", "zssj", "kf", "biaoji", "qianzhuang", "biaoju"]


# ---------------------------------------------------------------- 数据库
def sql(stmt: str, *, fetch: bool = True) -> list[list[str]]:
    p = subprocess.run(
        [MYSQL, "-uroot", "-p123456", "--default-character-set=gbk", "--batch", "--raw", DB, "-e", stmt],
        capture_output=True,
    )
    out = p.stdout.decode("gbk", errors="replace")
    err = p.stderr.decode("gbk", errors="replace")
    if p.returncode != 0 or "ERROR" in err:
        raise RuntimeError(f"mysql failed: {err.strip()}\nSQL: {stmt[:200]}")
    rows = [line.split("\t") for line in out.splitlines() if line]
    return rows[1:] if (fetch and rows) else rows


def columns(table: str) -> list[tuple[str, str]]:
    rows = sql(
        f"select column_name, data_type from information_schema.columns where table_schema='{DB}' and table_name='{table}' order by ordinal_position"
    )
    return [(r[0], r[1]) for r in rows]


def clone(src: int, dst: int) -> None:
    cleanup(dst, quiet=True)
    for t in CLONE_TABLES:
        cols = [c for c, _ in columns(t)]
        if not cols or "jyid" not in cols:
            continue
        sql(f"drop table if exists _jy_tmp", fetch=False)
        try:
            sql(f"create table _jy_tmp as select * from {t} where jyid={src}", fetch=False)
        except RuntimeError as e:
            # ypsx / zssj / biaoju 在这套库里只有 .frm、没有数据文件，访问会报「表不存在」
            print(f"  skip {t}: {str(e).splitlines()[0]}")
            continue
        n = int(sql("select count(*) from _jy_tmp")[0][0])
        if n:
            sets = [f"jyid={dst}"]
            if t == "renwu":
                # 名字用纯数字：用字母名的克隆号登录后原版不发登录序列（原因待查）
                sets += [f"name='{dst}'", f"nickname='{dst % 1000}'"]
            sql(f"update _jy_tmp set {', '.join(sets)}", fetch=False)
            id_col = next((c for c in ("id", "ID") if c in cols), None)
            if id_col:
                sql(f"alter table _jy_tmp modify {id_col} int null", fetch=False)
                sql(f"update _jy_tmp set {id_col}=null", fetch=False)
            sql(f"insert into {t} select * from _jy_tmp", fetch=False)
        sql("drop table if exists _jy_tmp", fetch=False)
        print(f"  cloned {t}: {n} rows")


def cleanup(dst: int, quiet: bool = False) -> None:
    for t in CLONE_TABLES:
        try:
            sql(f"delete from {t} where jyid={dst}", fetch=False)
        except RuntimeError:
            pass
    if not quiet:
        print(f"cleaned up jyid={dst}")


# ---------------------------------------------------------------- 登录
PASSWORD = {"value": None}  # 登录包末尾的 ASCII 是明文密码（测试号的密码恰好等于 jyid）


def login_stream(host: str, port: int, jyid: int, settle: float = 1.2) -> list[tuple[int, bytes, bool]]:
    s = socket.create_connection((host, port), timeout=5)
    s.settimeout(0.1)
    rx = FrameReader("s2c", resync=True)
    frames: list[tuple[int, bytes, bool]] = []

    def drain(seconds: float, stop_op: int | None = None) -> None:
        end = time.time() + seconds
        while time.time() < end:
            try:
                data = s.recv(65536)
            except socket.timeout:
                continue
            except OSError:
                return
            if not data:
                return
            for f in rx.feed(data):
                frames.append((f.opcode, f.payload, f.wide))
                if stop_op is not None and f.opcode == stop_op:
                    return

    try:
        payload = struct.pack("<II", jyid, UNKNOWN_CONST) + str(PASSWORD["value"] or jyid).encode("ascii")
        s.sendall(encode_c2s(0x01, payload, key=KEY_C2S_HANDSHAKE, seq=1, wide=False))
        drain(1.5, stop_op=0x01)
        if not frames or frames[0][0] != 0x01:
            return []
        s.sendall(encode_c2s(0x19, b"\x00", key=c2s_key(2), seq=2, wide=False))
        drain(settle + 2.0, stop_op=0xA9)
    finally:
        s.close()
    return frames


# ---------------------------------------------------------------- 对比
def diff_streams(a, b):
    """返回 [(frame_index, opcode, [changed offsets])]；长度不同返回 None。"""
    if len(a) != len(b) or any(x[0] != y[0] or len(x[1]) != len(y[1]) for x, y in zip(a, b)):
        return None
    out = []
    for i, (x, y) in enumerate(zip(a, b)):
        offs = [k for k in range(len(x[1])) if x[1][k] != y[1][k]]
        if offs:
            out.append((i, x[0], offs))
    return out


def describe_change(a, b, changes):
    parts = []
    for i, op, offs in changes:
        groups, cur = [], [offs[0]]
        for o in offs[1:]:
            if o == cur[-1] + 1:
                cur.append(o)
            else:
                groups.append(cur)
                cur = [o]
        groups.append(cur)
        for g in groups:
            parts.append(
                {
                    "frame": i,
                    "opcode": f"0x{op:02x}",
                    "offset": g[0],
                    "width": len(g),
                    "old": a[i][1][g[0] : g[-1] + 1].hex(" "),
                    "new": b[i][1][g[0] : g[-1] + 1].hex(" "),
                }
            )
    return parts


INT_TYPES = {"int", "bigint", "tinyint", "smallint", "mediumint"}
STR_TYPES = {"char", "varchar", "text"}


PATTERN_BY_WIDTH = {1: 57, 2: 1234, 3: 123456, 4: 305419896, 5: 1234567890}
IGNORE = {(1, 0)}  # 0x1E 载荷第 0 字节是随时间递增的计数（不是校验和）


def probe2(args) -> int:
    """第二轮：(a) 已定位的列用按宽度挑选的合理值验证「原样小端写入」；(b) 结构变化的列逐个试小值。"""
    first = json.loads(Path(args.inp).read_text(encoding="utf-8"))
    table = first["table"]
    baseline = None
    for _ in range(2):
        baseline = login_stream(args.host, args.port, args.dst)
        time.sleep(2.5)
    cols = {c: t for c, t in columns(table)}
    allcols = list(cols)
    orig_row = sql(f"select * from {table} where jyid={args.dst} limit 1")[0]
    out = {}
    for name, info in first["columns"].items():
        dtype = cols.get(name, "")
        if dtype not in INT_TYPES or name == "jyid":
            continue
        orig = orig_row[allcols.index(name)]
        locs = []
        if "changes" in info:
            locs = [(c["frame"], c["offset"], c["width"]) for c in info["changes"] if (c["frame"], c["offset"]) not in IGNORE]
            if not locs:
                out[name] = {"kind": "not-in-stream"}
                continue
            trials = sorted({PATTERN_BY_WIDTH.get(w, 57) for _, _, w in locs}, key=lambda v: -v)[:1]
            kind = "validate"
        elif info.get("result") == "structure-changed":
            trials = [1, 0, 2, 3]
            kind = "structural"
        else:
            out[name] = {"kind": "no-change-seen"}
            continue
        entry = {"kind": kind, "orig": orig, "trials": []}
        for v in trials:
            sql(f"update {table} set {name}={v} where jyid={args.dst}", fetch=False)
            time.sleep(2.5)
            try:
                got = login_stream(args.host, args.port, args.dst)
            finally:
                sql(f"update {table} set {name}={orig} where jyid={args.dst}", fetch=False)
            d = diff_streams(baseline, got) if got else None
            t = {"value": v}
            if d is None:
                t["result"] = "structure-changed" if got else "no-stream"
                if got:
                    t["frame_lengths"] = [len(p) for _, p, _ in got]
            else:
                d = [(i, op, [x for x in offs if (i, x) not in IGNORE and (i, x) != (10, 6)]) for i, op, offs in d]
                d = [x for x in d if x[2]]
                t["changes"] = describe_change(baseline, got, d)
                if kind == "validate":
                    ok = []
                    for fr, off, w in locs:
                        exp = (v & ((1 << (8 * w)) - 1)).to_bytes(w, "little").hex(" ")
                        seen = got[fr][1][off : off + w].hex(" ")
                        ok.append({"frame": fr, "offset": off, "width": w, "expected": exp, "seen": seen, "identity": exp == seen})
                    t["check"] = ok
            entry["trials"].append(t)
            if kind == "structural" and "changes" in t:
                break
        out[name] = entry
        if kind == "validate":
            tt = entry["trials"][0].get("check") or []
            tag = "identity" if tt and all(x["identity"] for x in tt) else ("MISMATCH " + json.dumps(tt, ensure_ascii=False) if tt else entry["trials"][0].get("result", "?"))
        else:
            ok = [t for t in entry["trials"] if "changes" in t]
            tag = (f"works with {ok[0]['value']}: " + ", ".join(f"f{c['frame']}@{c['offset']}+{c['width']}" for c in ok[0]["changes"])) if ok else "all trials change structure"
        print(f"{table}.{name:<20} {kind:<10} {tag}", flush=True)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps({"table": table, "columns": out}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["clone", "baseline", "probe", "probe2", "cleanup"])
    ap.add_argument("--in", dest="inp", default=None, help="probe2 的输入（probe 的输出 JSON）")
    ap.add_argument("--src", type=int, default=8617293)
    ap.add_argument("--dst", type=int, default=9999001)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=6731)
    ap.add_argument("--table", default="renwu")
    ap.add_argument("--cols", default=None, help="只探测这些列，逗号分隔")
    ap.add_argument("--out", default=None)
    ap.add_argument("--password", default=None, help="登录用的明文密码；克隆号的密码是从 --src 复制来的，默认用 str(src)")
    ap.add_argument("--trials", default=None, help="probe 用这些值代替默认试探值，逗号分隔，如 0,2,3")
    args = ap.parse_args()
    PASSWORD["value"] = args.password or (str(args.src) if args.dst != args.src else None)

    if args.cmd == "clone":
        clone(args.src, args.dst)
        return 0
    if args.cmd == "cleanup":
        cleanup(args.dst)
        return 0
    if args.cmd == "probe2":
        return probe2(args)

    base = []
    for _ in range(3):
        base.append(login_stream(args.host, args.port, args.dst))
        time.sleep(2.5)  # 原版有单点登录：上一个连接刚断开时马上再登录会被拒
    ok = all(base) and all(len(b) == len(base[0]) for b in base)
    print(f"baseline logins: frames per login = {[len(b) for b in base]}")
    if not ok:
        print("baseline failed (no handshake / stream); is the clone created and the original server running?")
        return 1
    dd = [diff_streams(base[0], b) for b in base[1:]]
    for k, d in enumerate(dd, 1):
        print(f"  baseline #0 vs #{k}: " + ("structure differs" if d is None else ("identical" if not d else f"{sum(len(o) for _, _, o in d)} bytes differ: " + str([(i, f'0x{op:02x}', o[:6]) for i, op, o in d])))
        )
    sizes = [(i, f"0x{op:02x}", len(p), "L" if w else "S") for i, (op, p, w) in enumerate(base[0])]
    print("  stream:", sizes)
    if args.cmd == "baseline":
        return 0

    # ---- probe
    baseline = base[0]
    noisy = set()
    for d in dd:
        if d:
            for i, op, offs in d:
                noisy.update((i, o) for o in offs)
    cols = columns(args.table)
    if args.cols:
        want = set(args.cols.split(","))
        cols = [c for c in cols if c[0] in want]
    orig_row = sql(f"select * from {args.table} where jyid={args.dst} limit 1")[0]
    allcols = [c for c, _ in columns(args.table)]
    results = {}
    for name, dtype in cols:
        if name == "jyid":
            continue
        orig = orig_row[allcols.index(name)]
        if dtype in INT_TYPES:
            trials = [("168496141" if dtype != "tinyint" else "13"), "3085", "77", "5"]
        elif dtype in STR_TYPES:
            trials = ["QZQZ"]
        else:
            continue
        if args.trials:
            trials = args.trials.split(",")
        found = None
        for v in trials:
            if v == orig:
                continue
            q = f"'{v}'" if dtype in STR_TYPES else v
            sql(f"update {args.table} set {name}={q} where jyid={args.dst}", fetch=False)
            time.sleep(2.5)
            try:
                got = login_stream(args.host, args.port, args.dst)
            finally:
                o = "NULL" if orig == "NULL" else (f"'{orig}'" if dtype in STR_TYPES else orig)
                sql(f"update {args.table} set {name}={o} where jyid={args.dst}", fetch=False)
            d = diff_streams(baseline, got) if got else None
            if d is None:
                found = {"value": v, "result": "structure-changed" if got else "no-stream", "frames_before": len(baseline), "frames_after": len(got)}
                continue  # 换下一个试探值（大数常被服务端当成越界而改变结构）
            d = [(i, op, [x for x in offs if (i, x) not in noisy]) for i, op, offs in d]
            d = [t for t in d if t[2]]
            if d:
                found = {"value": v, "changes": describe_change(baseline, got, d)}
                break
        results[name] = found or {"result": "no-change-seen"}
        tag = "no change" if "result" in results[name] and results[name]["result"] == "no-change-seen" else (
            results[name].get("result") or ", ".join(f"f{c['frame']}@{c['offset']}+{c['width']}" for c in results[name]["changes"])
        )
        print(f"{args.table}.{name:<18} {dtype:<8} -> {tag}", flush=True)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps({"table": args.table, "baseline_stream": sizes, "columns": results}, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
