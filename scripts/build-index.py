#!/usr/bin/env python3
"""Regenerate the skill catalogue at skills/README.md.

Two reasons it lives there rather than in the root README:

  * GitHub renders a directory's README when you browse it, so the catalogue is
    where someone looking for a skill actually is.
  * The root README is guidance — the working rules, install, credentials. Forty
    generated lines in the middle of it push all of that down the page.

Agents do not need this file at all. The Agent Skills spec loads every skill's
name and description at startup, so the descriptions *are* the index. This is for
humans browsing the repo, and for tools that clone without skill support.

Grouping comes from each skill's `metadata.category`, so adding a skill needs no
change here.

Usage:
    python3 scripts/build-index.py          # rewrite skills/README.md
    python3 scripts/build-index.py --check  # fail if it would change (for CI)

Licence: GPL-2.0-or-later
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CATALOGUE = REPO / "skills" / "README.md"

BEGIN = "<!-- BEGIN SKILL INDEX -->"
END = "<!-- END SKILL INDEX -->"

# Order and blurbs for the catalogue. A category with no skills is skipped.
CATEGORIES = [
    ("orientation", "Start here",
     "The map, and turning a vague complaint into a diagnosis."),
    ("access", "Getting hold of a Kodi",
     "Finding one, driving it, and seeing what it did."),
    ("diagnosis", "Working out what happened",
     "Logs, freezes, defects, and isolating a bad add-on."),
    ("playback", "Playback and streams",
     "Getting Kodi to play the right thing, in the right place, at the right rate."),
    ("python-addon", "Writing a Python add-on",
     "The manifest, the lifecycle, and the ways an add-on hangs Kodi."),
    ("binary-addon", "Writing a binary add-on",
     "Building it so it loads on someone else's machine."),
    ("skinning", "Skinning",
     "Skin XML and the coordinate spaces behind it."),
    ("kodi-data", "Kodi's own data",
     "The databases and the artwork cache."),
    ("shipping", "Shipping it",
     "Versions, releases, and getting a change accepted upstream."),
    ("adjacent", "Adjacent systems",
     "Not Kodi, but things Kodi add-ons routinely talk to."),
    ("workflow", "Working with this repo",
     "Contributing what a session learned, and keeping the repo from silting up."),
]

FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)

HEADER = """# Skill catalogue

Every skill is one topic. Load the one you need — you do not need to read this
file first, and neither does an agent: the [Agent Skills
spec](https://agentskills.io/specification) loads every skill's name and
description at startup, so an agent already knows what is here.

This catalogue is for browsing. It is generated from the skills themselves by
`scripts/build-index.py`, grouped by each skill's `metadata.category`.

See [`../README.md`](../README.md) for how to install and use these, and
[`../CONTRIBUTING.md`](../CONTRIBUTING.md) for the bar a new one has to clear.
"""

FOOTER = """
Add-on-specific knowledge lives in [`../addons/`](../addons/); knowledge about
non-Kodi systems lives in [`../adjacent/`](../adjacent/).
"""


def first_sentence(description: str) -> str:
    text = " ".join(description.split())
    m = re.search(r"(?<![A-Z])(?<!\be\.g)(?<!\bi\.e)\.\s", text)
    if m:
        text = text[: m.start() + 1]
    return text.rstrip()


def frontmatter(path: Path) -> dict:
    m = FRONTMATTER_RE.match(path.read_text(encoding="utf-8"))
    if not m:
        return {}
    lines = m.group(1).split("\n")
    out: dict = {}
    for i, line in enumerate(lines):
        if line.startswith("description:"):
            value = line.partition(":")[2].strip()
            if value not in (">", "|", ">-", "|-"):
                out["description"] = value.strip("\"'")
                continue
            collected = []
            for cont in lines[i + 1:]:
                if not cont.strip():
                    continue
                if not cont.startswith((" ", "\t")):
                    break
                collected.append(cont.strip())
            out["description"] = " ".join(collected)
        elif re.match(r"^\s+category:", line):
            out["category"] = line.partition(":")[2].strip().strip("\"'")
    return out


def build() -> str:
    found: dict[str, list[tuple[str, str, str]]] = {}
    for directory in ("skills", "addons", "adjacent"):
        root = REPO / directory
        if not root.is_dir():
            continue
        for skill in sorted(root.rglob("SKILL.md")):
            meta = frontmatter(skill)
            cat = meta.get("category", "uncategorised")
            rel = skill.relative_to(REPO / "skills") if directory == "skills" \
                else Path("..") / skill.relative_to(REPO)
            found.setdefault(cat, []).append(
                (skill.parent.name, str(rel), first_sentence(meta.get("description", "")))
            )

    out: list[str] = []
    for key, title, blurb in CATEGORIES:
        entries = found.pop(key, [])
        if not entries:
            continue
        out += [f"## {title}", "", f"*{blurb}*", ""]
        for name, rel, desc in entries:
            out.append(f"- [`{name}`]({rel}) — {desc}" if desc else f"- [`{name}`]({rel})")
        out.append("")

    for leftover, entries in sorted(found.items()):
        out += [f"## {leftover}", ""]
        for name, rel, desc in entries:
            out.append(f"- [`{name}`]({rel}) — {desc}")
        out.append("")

    return "\n".join(out).rstrip() + "\n" if out else "*No skills yet.*\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if the catalogue is out of date instead of rewriting it")
    args = ap.parse_args()

    updated = f"{HEADER}\n{BEGIN}\n\n{build()}\n{END}\n{FOOTER}"
    current = CATALOGUE.read_text(encoding="utf-8") if CATALOGUE.exists() else ""

    if updated == current:
        print("skills/README.md is up to date")
        return 0
    if args.check:
        print("skills/README.md is out of date — run scripts/build-index.py",
              file=sys.stderr)
        return 1

    CATALOGUE.parent.mkdir(parents=True, exist_ok=True)
    CATALOGUE.write_text(updated, encoding="utf-8")
    print("skills/README.md regenerated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
