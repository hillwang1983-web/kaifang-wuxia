"""把原版 MySQL 库里角色相关表的列默认值导出成 data/defaults.json。

    python tools/dump_defaults.py

新建角色时原版只 `insert into renwu (jyid,name)`，其余列全靠表结构里的 DEFAULT，所以新服务端要有同一份默认值。
值都按字符串存（和 snapshot / importer 的行格式一致）；没有默认值（NULL）的列存 null。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import layout_probe as lp  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "data" / "defaults.json"
TABLES = ["renwu", "char_equip", "jineng", "item", "account"]


def main() -> None:
    out: dict[str, dict[str, str | None]] = {}
    for t in TABLES:
        rows = lp.sql(
            "select column_name, column_default from information_schema.columns "
            f"where table_schema='{lp.DB}' and table_name='{t}' order by ordinal_position"
        )
        out[t] = {name: (None if d == "NULL" else d) for name, d in rows}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print({t: len(c) for t, c in out.items()}, "->", OUT)


if __name__ == "__main__":
    main()
