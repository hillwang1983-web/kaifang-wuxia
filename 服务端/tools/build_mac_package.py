"""把新服务端打成 macOS 部署包（zip，UTF-8 文件名，.sh 带可执行位）。

    python tools/build_mac_package.py            # 完整包：第一次部署用，带角色库快照
    python tools/build_mac_package.py --update   # 更新包：不带角色库，Mac 上跑包里的 update.sh

包里有：jyserver/、data/（角色库用 SQLite 备份接口取一致快照，服务端开着也能打）、
原版数据/data + 原版数据/config（从原版服务端目录复制）、tests/、tools/、docs/、start.sh、部署说明.md。
不带 captures/（含账号录像）、backups/、scratch_*、__pycache__。
"""

from __future__ import annotations

import argparse
import sqlite3
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ORIGINAL = Path(r"C:\游戏\网金最原始文件\网金最原始文件\服务端")
MAC = ROOT / "deploy" / "mac"

SKIP_DIRS = {"__pycache__"}
EXECUTABLE = {"start.sh", "update.sh"}


def iter_files(base: Path):
    for p in sorted(base.rglob("*")):
        if p.is_file() and not SKIP_DIRS.intersection(p.relative_to(base).parts) and p.suffix != ".pyc":
            yield p


def add(zf: zipfile.ZipFile, src: Path, arc: str) -> None:
    data = src.read_bytes()
    if arc.endswith(".sh"):
        data = data.replace(b"\r\n", b"\n")  # Mac 上 CRLF 的脚本跑不起来
    info = zipfile.ZipInfo(arc, date_time=time.localtime(src.stat().st_mtime)[:6])
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3  # Unix，external_attr 里的权限位才会被 Mac 的解压工具认
    mode = 0o755 if Path(arc).name in EXECUTABLE else 0o644
    info.external_attr = (0o100000 | mode) << 16
    zf.writestr(info, data)


def snapshot_db(src: Path, dst: Path) -> None:
    s = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    d = sqlite3.connect(dst)
    try:
        s.backup(d)
    finally:  # `with` 只管事务不关连接，Windows 上临时目录会删不掉
        d.close()
        s.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(ROOT / "dist"))
    ap.add_argument("--update", action="store_true", help="更新包：不带角色库，在 Mac 上用包里的 update.sh 装到已有目录")
    args = ap.parse_args()

    stamp = time.strftime("%Y%m%d-%H%M")
    top = f"jyserver-mac-update-{stamp}" if args.update else "jyserver-mac"
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    zpath = out / (f"{top}.zip" if args.update else f"{top}-{stamp}.zip")

    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "chars.sqlite"
        if not args.update:
            snapshot_db(ROOT / "data" / "chars.sqlite", db)

        with zipfile.ZipFile(zpath, "w") as zf:  # 非 ASCII 文件名自动打 UTF-8 标志
            for sub in ("jyserver", "data", "tests", "tools", "docs"):
                for p in iter_files(ROOT / sub):
                    if p.parent == ROOT / "data" and p.name.startswith("chars.sqlite"):
                        continue  # 角色库（及 -journal/-wal）只在完整包里放快照
                    add(zf, p, f"{top}/{p.relative_to(ROOT).as_posix()}")
            if not args.update:
                add(zf, db, f"{top}/data/chars.sqlite")
            zf.writestr(f"{top}/VERSION.txt", f"{stamp}\n")
            add(zf, ROOT / "README.md", f"{top}/README.md")
            for name in ("data", "config"):
                for p in iter_files(ORIGINAL / name):
                    add(zf, p, f"{top}/原版数据/{p.relative_to(ORIGINAL).as_posix()}")
            for p in iter_files(MAC):
                add(zf, p, f"{top}/{p.relative_to(MAC).as_posix()}")

    with zipfile.ZipFile(zpath) as zf:
        n = len(zf.namelist())
    print(f"{zpath}  {n} 个文件  {zpath.stat().st_size / 1024 / 1024:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
