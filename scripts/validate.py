#!/usr/bin/env python3
"""Validate kodi-drive skills.

Enforces the contribution bar mechanically, because prose alone does not hold:

  * frontmatter schema, including the flat `metadata.verified-*` keys the
    Agent Skills spec requires (string values only) and a valid category
  * no hedging language outside an `## Open questions` section
  * skills stay small enough that loading one is cheap

Exit 0 if everything passes, 1 otherwise. No dependencies beyond the stdlib.

Licence: GPL-2.0-or-later
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILL_DIRS = ("skills", "addons", "adjacent")

MAX_LINES = 500
WARN_LINES = 300
STALE_DAYS = 400  # ~13 months, so a yearly re-verify does not trip it

VALID_METHODS = {"observed", "sourced", "inferred"}

# Kodi releases, for validating `metadata.verified-kodi`. Extend as versions ship.
KNOWN_KODI = {
    "17": "Krypton", "18": "Leia", "19": "Matrix",
    "20": "Nexus", "21": "Omega", "22": "Piers",
}
CURRENT_STABLE_MAJOR = "21"

# Words that turn a guess into something a reader will act on. The whole point of
# this repo is that skills are trusted absolutely, so these have no place in one.
# `## Open questions` sections are exempt: uncertainty needs a legal home, or it
# gets laundered into confident prose instead, which is worse.
HEDGES = [
    r"probably", r"should work", r"i think", r"might be", r"seems to",
    r"presumably", r"in theory", r"likely", r"may need to", r"appears to",
    r"i believe", r"not sure", r"possibly", r"perhaps", r"i suspect",
    r"as far as i know", r"afaik", r"maybe",
]
HEDGE_RE = re.compile(r"\b(" + "|".join(HEDGES) + r")\b", re.IGNORECASE)

FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)


@dataclass
class Findings:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def error(self, path: Path, line: int | None, msg: str) -> None:
        loc = f"{path.relative_to(REPO)}" + (f":{line}" if line else "")
        self.errors.append(f"{loc}: {msg}")

    def warn(self, path: Path, line: int | None, msg: str) -> None:
        loc = f"{path.relative_to(REPO)}" + (f":{line}" if line else "")
        self.warnings.append(f"{loc}: {msg}")


def parse_frontmatter(text: str) -> tuple[dict, int] | None:
    """Return (mapping, body_start_line) or None if absent.

    A deliberately small YAML subset: scalars, block scalars, and flow lists,
    nested by indentation. Enough for skill frontmatter, and it keeps the repo
    dependency-free so CI and a contributor's laptop behave identically.
    """
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None
    body_start = text[: m.end()].count("\n") + 1

    root: dict = {}
    stack: list[tuple[int, dict]] = [(-1, root)]
    pending_block: tuple[str, dict, int] | None = None
    block_lines: list[str] = []

    for raw in m.group(1).split("\n"):
        if not raw.strip():
            if pending_block:
                block_lines.append("")
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        stripped = raw.strip()

        if pending_block:
            key, parent, block_indent = pending_block
            if indent > block_indent:
                block_lines.append(stripped)
                continue
            parent[key] = " ".join(x for x in block_lines if x)
            pending_block, block_lines = None, []

        if stripped.startswith("- "):
            while stack and stack[-1][0] >= indent:
                stack.pop()
            continue  # list items under a key are handled via flow lists below

        if ":" not in stripped:
            continue
        key, _, value = stripped.partition(":")
        key, value = key.strip(), value.strip()

        while len(stack) > 1 and stack[-1][0] >= indent:
            stack.pop()
        parent = stack[-1][1]

        if value in (">", "|", ">-", "|-"):
            pending_block = (key, parent, indent)
            block_lines = []
        elif value == "":
            child: dict = {}
            parent[key] = child
            stack.append((indent, child))
        elif value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            parent[key] = [
                x.strip().strip("\"'") for x in inner.split(",") if x.strip()
            ] if inner else []
        else:
            parent[key] = value.strip("\"'")

    if pending_block:
        key, parent, _ = pending_block
        parent[key] = " ".join(x for x in block_lines if x)

    return root, body_start


def open_questions_span(lines: list[str], offset: int) -> set[int]:
    """Line numbers (1-based, file coords) inside an `## Open questions` section.

    Everything from that heading until the next heading of the same or higher
    level is exempt from the hedge lint.
    """
    exempt: set[int] = set()
    in_section = False
    for i, line in enumerate(lines):
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            level, title = len(m.group(1)), m.group(2).strip().lower()
            if re.match(r"open questions?|unverified|unknowns?", title):
                in_section, section_level = True, level
                continue
            if in_section and level <= section_level:
                in_section = False
        if in_section:
            exempt.add(offset + i)
    return exempt


def code_block_lines(lines: list[str], offset: int) -> set[int]:
    """Line numbers inside fenced code blocks — never linted for hedges."""
    inside: set[int] = set()
    fence = None
    for i, line in enumerate(lines):
        m = re.match(r"^\s*(```+|~~~+)", line)
        if m:
            token = m.group(1)
            if fence is None:
                fence = token
                inside.add(offset + i)
                continue
            if token[0] == fence[0] and len(token) >= len(fence):
                inside.add(offset + i)
                fence = None
                continue
        if fence is not None:
            inside.add(offset + i)
    return inside


VALID_CATEGORIES = {
    "orientation", "access", "diagnosis", "playback", "python-addon",
    "binary-addon", "skinning", "kodi-data", "shipping", "adjacent",
    "workflow",
}

# `workflow` skills are about operating this repo — contributing, auditing — not
# about Kodi. They make no version- or platform-dependent claim, so demanding
# `verified-kodi: "21.3 Omega"` from one would force a contributor to state
# something untrue in the exact field this repo exists to keep honest.
#
# `verified-date` and `verified-method` still apply: the procedure was run, on a
# day, and that is worth recording.
NO_KODI_CLAIM = {"workflow"}


def check_verified(meta: dict, path: Path, f: Findings) -> None:
    """Validate the flat `metadata` map.

    The Agent Skills spec defines `metadata` as a map from string keys to string
    values, so the fields are flat `verified-*` keys rather than a nested block.
    Multi-valued fields are comma-separated within one string.
    """
    if not isinstance(meta, dict) or not any(
        k.startswith("verified-") for k in meta
    ):
        f.error(path, None, "frontmatter is missing the `metadata.verified-*` keys "
                            "(need: verified-kodi, verified-platform, "
                            "verified-date, verified-method)")
        return

    category = meta.get("category")
    if not category:
        f.error(path, None, "`metadata.category` is required — it groups the skill "
                            f"in the catalogue. One of: {', '.join(sorted(VALID_CATEGORIES))}")
    elif category not in VALID_CATEGORIES:
        f.error(path, None, f"`metadata.category` is {category!r}; must be one of "
                            f"{', '.join(sorted(VALID_CATEGORIES))}")

    for key, value in meta.items():
        if not isinstance(value, str):
            f.error(path, None, f"`metadata.{key}` must be a string — the Agent "
                                "Skills spec allows only string values in metadata")

    verified = {
        k[len("verified-"):]: v
        for k, v in meta.items()
        if k.startswith("verified-") and isinstance(v, str)
    }

    claims_kodi = category not in NO_KODI_CLAIM

    kodi = [x.strip() for x in verified.get("kodi", "").split(",") if x.strip()]
    if not kodi:
        if claims_kodi:
            f.error(path, None, "`metadata.verified-kodi` is required — list the versions "
                                "you actually tested, not a range")
    else:
        for v in kodi:
            major = re.match(r"^(\d+)", str(v))
            if not major:
                f.error(path, None, f"`verified-kodi` entry {v!r} does not start with a "
                                    "major version, e.g. '21.3 Omega'")
            elif major.group(1) not in KNOWN_KODI:
                f.warn(path, None, f"`verified-kodi` entry {v!r} names an unrecognised "
                                   f"Kodi major — known: {', '.join(sorted(KNOWN_KODI))}")
        majors = {re.match(r"^(\d+)", str(v)).group(1)
                  for v in kodi if re.match(r"^(\d+)", str(v))}
        if majors and CURRENT_STABLE_MAJOR not in majors:
            f.warn(path, None, f"not verified against current stable Kodi "
                               f"{CURRENT_STABLE_MAJOR} ({KNOWN_KODI[CURRENT_STABLE_MAJOR]})")

    if not verified.get("platform") and claims_kodi:
        f.error(path, None, "`metadata.verified-platform` is required — Kodi behaviour "
                            "genuinely diverges across platforms")

    method = verified.get("method")
    if not method:
        f.error(path, None, "`metadata.verified-method` is required "
                            f"({'/'.join(sorted(VALID_METHODS))})")
    elif method not in VALID_METHODS:
        f.error(path, None, f"`metadata.verified-method` is {method!r}, must be one of "
                            f"{', '.join(sorted(VALID_METHODS))}")

    date = verified.get("date")
    if not date:
        f.error(path, None, "`metadata.verified-date` is required (YYYY-MM-DD)")
    else:
        try:
            when = dt.date.fromisoformat(str(date))
        except ValueError:
            f.error(path, None, f"`metadata.verified-date` {date!r} is not YYYY-MM-DD")
        else:
            age = (dt.date.today() - when).days
            if age > STALE_DAYS:
                f.warn(path, None, f"last verified {age} days ago — re-check against a "
                                   "current Kodi, or say so under '## Open questions'")
            if age < 0:
                f.error(path, None, f"`metadata.verified-date` {date} is in the future")


def check_skill(path: Path, f: Findings) -> None:
    text = path.read_text(encoding="utf-8")
    parsed = parse_frontmatter(text)
    if parsed is None:
        f.error(path, 1, "no YAML frontmatter — every skill needs at least "
                         "`description` and `metadata.verified`")
        return
    meta, body_start = parsed

    if not meta.get("description"):
        f.error(path, None, "frontmatter is missing `description` — it is the only thing "
                            "an agent sees before deciding to load the skill")
    else:
        desc = str(meta["description"])
        if len(desc) > 1400:
            f.warn(path, None, f"`description` is {len(desc)} chars; the skill listing "
                               "truncates around 1536, so put the use case first")
        if len(desc) < 40:
            f.warn(path, None, "`description` is very short — say what it is AND when to "
                               "reach for it, or agents will not load it at the right time")

    name = meta.get("name")
    if name and name != path.parent.name:
        f.error(path, None, f"frontmatter `name` is {name!r} but the directory is "
                            f"{path.parent.name!r} — they must match")

    check_verified(meta.get("metadata", {}), path, f)

    body_lines = text.split("\n")[body_start:]
    total = len(text.split("\n"))
    if total > MAX_LINES:
        f.error(path, None, f"{total} lines — over the {MAX_LINES} limit. Split it, or "
                            "move reference material to a sibling file and link it.")
    elif total > WARN_LINES:
        f.warn(path, None, f"{total} lines — consider splitting above {WARN_LINES}")

    exempt = open_questions_span(body_lines, body_start + 1)
    exempt |= code_block_lines(body_lines, body_start + 1)
    for i, line in enumerate(body_lines):
        lineno = body_start + 1 + i
        if lineno in exempt:
            continue
        m = HEDGE_RE.search(line)
        if m:
            f.error(path, lineno,
                    f"hedging language {m.group(0)!r} — if you are not sure, this is an "
                    "issue, not a skill. Or move it under '## Open questions'.")

    # Relative links between skills. A skill pointing at one that was renamed or
    # never written sends a reader somewhere that does not exist, and nothing
    # else in the toolchain would notice.
    for i, line in enumerate(body_lines):
        for m in re.finditer(r"\]\((\.\.?/[^)#]+)", line):
            target = (path.parent / m.group(1)).resolve()
            if not target.exists():
                f.error(path, body_start + 1 + i,
                        f"link target does not exist: {m.group(1)}")


def check_doc_links(f: Findings) -> None:
    """Relative links in the top-level docs, which point into skills/."""
    for name in ("README.md", "CONTRIBUTING.md"):
        doc = REPO / name
        if not doc.exists():
            continue
        for i, line in enumerate(doc.read_text(encoding="utf-8").split("\n"), 1):
            for m in re.finditer(r"\]\(((?!https?:|#|mailto:)[^)#]+)", line):
                target = m.group(1)
                # `../../issues/new?...` and friends are GitHub's relative repo
                # URLs, resolved by the web UI rather than by the filesystem.
                if re.match(r"\.\./\.\./(issues|pulls|discussions|wiki|blob|tree)\b",
                            target):
                    continue
                if not (REPO / target).exists():
                    f.error(doc, i, f"link target does not exist: {target}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*", type=Path,
                    help="specific SKILL.md files (default: all)")
    ap.add_argument("--strict", action="store_true",
                    help="treat warnings as errors")
    args = ap.parse_args()

    if args.paths:
        skills = [p.resolve() for p in args.paths]
    else:
        skills = sorted(
            p for d in SKILL_DIRS for p in (REPO / d).rglob("SKILL.md")
        )

    if not skills:
        print("no skills found yet — nothing to validate")
        return 0

    f = Findings()
    for path in skills:
        check_skill(path, f)

    # The top-level docs link into skills/ too, and a README pointing at a skill
    # that was never written is the first thing a new reader hits.
    if not args.paths:
        check_doc_links(f)

    for w in f.warnings:
        print(f"warning: {w}")
    for e in f.errors:
        print(f"ERROR:   {e}")

    n = len(skills)
    if f.errors:
        print(f"\n{len(f.errors)} error(s), {len(f.warnings)} warning(s) across {n} skill(s)")
        return 1
    if f.warnings and args.strict:
        print(f"\n{len(f.warnings)} warning(s) across {n} skill(s) (--strict)")
        return 1
    print(f"\nOK: {n} skill(s), {len(f.warnings)} warning(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
