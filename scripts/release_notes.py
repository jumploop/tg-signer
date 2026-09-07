#!/usr/bin/env python3
"""Extract release notes for a given version from CHANGELOG.md.

Usage:
    python scripts/release_notes.py 0.9.7
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def extract(version: str, changelog: Path) -> tuple[list[str], list[str]]:
    """Return (zh_lines, en_lines) for ``### <version>`` in CHANGELOG.md."""
    text = changelog.read_text(encoding="utf-8")

    # 段分隔:任何 ### 行都标志新段开始
    header_re = re.compile(r"^### .+$", re.MULTILINE)
    target_re = re.compile(rf"^### {re.escape(version)}\s*$")

    matches = list(header_re.finditer(text))
    if not matches:
        raise SystemExit(f"version {version} not found in {changelog}")

    sections: list[tuple[list[str], list[str]]] = []
    for idx, header in enumerate(matches):
        if not target_re.match(header.group(0)):
            continue
        start = header.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        block = text[start:end].rstrip("\n")
        lines = [line.rstrip() for line in block.splitlines() if line.strip()]
        sections.append(lines)

    if not sections:
        raise SystemExit(f"version {version} not found in {changelog}")
    if len(sections) >= 2:
        return sections[0], sections[1]
    return sections[0], []


def render(version: str, zh: list[str], en: list[str]) -> str:
    out: list[str] = [f"## v{version}", ""]
    out += ["### 中文", ""]
    out += zh
    out += ["", "### English", ""]
    out += en or ["_(no English entries)_"]
    return "\n".join(out)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    version = sys.argv[1]
    changelog = Path(__file__).resolve().parent.parent / "CHANGELOG.md"
    zh, en = extract(version, changelog)
    print(render(version, zh, en))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
