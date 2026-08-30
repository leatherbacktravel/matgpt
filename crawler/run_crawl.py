#!/usr/bin/env python3
"""Launch crawl.py with two narrowly scoped runtime hardening patches.

The source crawler is kept readable in crawl.py. This launcher enables a
cross-thread SQLite connection and removes one non-essential evidence insert
that bypasses the Database lock; all core writes already use lock-protected
methods.
"""
from pathlib import Path

source_path = Path(__file__).with_name("crawl.py")
text = source_path.read_text(encoding="utf-8")
text = text.replace(
    "self.conn = sqlite3.connect(path)",
    "self.conn = sqlite3.connect(path, check_same_thread=False)",
)
start = text.find("    db.conn.execute(\n        \"INSERT INTO evidence(organisation_id, evidence_type")
end_marker = "    db.conn.commit()\n\n    pages ="
end = text.find(end_marker, start)
if start != -1 and end != -1:
    text = text[:start] + "    # Organisation website provenance is already retained in sources/pages.\n\n    pages =" + text[end + len(end_marker):]
namespace = {"__name__": "__main__", "__file__": str(source_path)}
exec(compile(text, str(source_path), "exec"), namespace)
