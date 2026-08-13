#!/usr/bin/env python3
"""Regenerate the skill index in README.md from the skills themselves.

A hand-maintained index drifts, and a drifted index is worse than none — an
agent that trusts it goes looking for a skill that moved. This reads the actual
frontmatter, so the index cannot disagree with the tree.

Usage:
    python3 scripts/build-index.py          # rewrite README.md in place
    python3 scripts/build-index.py --check  # fail if it would change (for CI)

Licence: GPL-2.0-or-later
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
README = REPO / "README.md"

BEGIN = "<!-- BEGIN SKILL INDEX -->"
END = "<!-- END SKILL INDEX -->"

SECTIONS = [
    ("skills", "Skills", "General Kodi knowledge — true across add-ons and installs."),
    ("addons", "Add-ons", "Specific to one add-on or skin."),
    ("adjacent", "Adjacent systems",
     "Not Kodi, but things Kodi add-ons routinely talk to."),
]

FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)


def first_sentence(description: str) -> str:
    """One line for the index. The full description stays in the skill."""
    text = " ".join(description.split())
    # Split on sentence end, but not on "e.g." and friends.
    m = re.search(r"(?<![A-Z])(?<!\be\.g)(?<!\bi\.e)\.\s", text)
    if m:
        text = text[: m.start() + 1]
    return text.rstrip()


def read_description(path: Path) -> str:
    m = FRONTMATTER_RE.match(path.read_text(encoding="utf-8"))
    if not m:
        return ""
    block = m.group(1)

    # description may be a plain scalar or a `>` block.
    lines = block.split("\n")
    for i, line in enumerate(lines):
        if not line.startswith("description:"):
            continue
        value = line.partition(":")[2].strip()
        if value not in (">", "|", ">-", "|-"):
            return value.strip("\"'")
        collected = []
        for cont in lines[i + 1:]:
            if not cont.strip():
                continue
            if not cont.startswith((" ", "\t")):
                break
            collected.append(cont.strip())
        return " ".join(collected)
    return ""


def build() -> str:
    out: list[str] = []
    for directory, title, blurb in SECTIONS:
        root = REPO / directory
        skills = sorted(root.rglob("SKILL.md")) if root.is_dir() else []
        if not skills:
            continue
        out.append(f"### {title}")
        out.append("")
        out.append(f"*{blurb}*")
        out.append("")
        for skill in skills:
            name = skill.parent.name
            desc = first_sentence(read_description(skill))
            rel = skill.relative_to(REPO)
            out.append(f"- [`{name}`]({rel}) — {desc}" if desc
                       else f"- [`{name}`]({rel})")
        out.append("")

    if not out:
        return "*No skills yet.*\n"
    return "\n".join(out).rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if README.md is out of date instead of rewriting it")
    args = ap.parse_args()

    text = README.read_text(encoding="utf-8")
    if BEGIN not in text or END not in text:
        print(f"error: README.md is missing the {BEGIN} / {END} markers",
              file=sys.stderr)
        return 2

    before, _, rest = text.partition(BEGIN)
    _, _, after = rest.partition(END)
    updated = f"{before}{BEGIN}\n\n{build()}\n{END}{after}"

    if updated == text:
        print("README.md skill index is up to date")
        return 0

    if args.check:
        print("README.md skill index is out of date — run scripts/build-index.py",
              file=sys.stderr)
        return 1

    README.write_text(updated, encoding="utf-8")
    print("README.md skill index regenerated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
