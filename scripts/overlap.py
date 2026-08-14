#!/usr/bin/env python3
"""Find skills that cover the same ground.

Duplication is the failure mode this repo is most likely to die of, and it is
invisible to every other check: two skills that each half-cover a topic both
validate, both scrub clean, and together are worse than either alone, because a
reader now has to find both and reconcile them.

Nobody re-reads 45 skills before writing the 46th. So this does it mechanically.

**How.** A skill's distinctive content is its identifiers — `CJobManager`,
`Player.SetTempo`, `reuselanguageinvoker`, `special://masterprofile`. Prose about
Kodi is generic; the symbols are not. So each skill is fingerprinted by the
identifiers in its body, weighted by how rare each one is across the repo
(a symbol in two skills is a signal; one in twenty is vocabulary).

**What it does not do.** It cannot tell duplication from a legitimate
cross-reference — `kodi-triage` names half the repo on purpose. It surfaces
pairs worth a human deciding about. Read the shared symbols, not the score.

Usage:
    python3 scripts/overlap.py                  # rank every pair
    python3 scripts/overlap.py --against F...   # nearest neighbours of F (for a PR)
    python3 scripts/overlap.py --top 20         # how many pairs to print
    python3 scripts/overlap.py --markdown       # for $GITHUB_STEP_SUMMARY

Licence: GPL-2.0-or-later
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILL_DIRS = ("skills", "addons", "adjacent")

# A symbol in more than this fraction of skills is repo vocabulary, not a claim
# about anything. `kodi-remote` appears everywhere and means nothing here.
MAX_DOC_FRACTION = 0.30

# Below this, the shared symbols are coincidence. Calibrated against the repo as
# it stood when this was written: real pairs scored well above it.
MIN_SCORE = 3.0

FRONTMATTER_RE = re.compile(r"\A---\r?\n.*?\r?\n---\r?\n", re.DOTALL)

# Shapes that carry meaning in Kodi content. Prose does not accidentally produce
# any of these, which is what makes them a usable fingerprint.
PATTERNS = [
    re.compile(r"\b\w+::\w+"),                    # CJobManager::OnJobComplete
    re.compile(r"\b[A-Z][A-Za-z0-9]*\.[A-Z][A-Za-z0-9]*\b"),  # Player.SetTempo
    re.compile(r"\bC[A-Z][A-Za-z0-9]{3,}\b"),     # CServiceBroker
    re.compile(r"\b[a-z]+://[a-z]*"),             # special://
    re.compile(r"\b[a-z]+\.[a-z]+\.[a-z.]+\b"),   # inputstream.adaptive
    re.compile(r"\b[A-Z][A-Z0-9_]{4,}\b"),        # WINDOW_HOME, ACTION_RELOAD_KEYMAPS
    re.compile(r"\b[a-z]+_[a-z_]+\b"),            # reuselanguageinvoker-ish snake
]

# Markdown that would otherwise fingerprint a skill by its neighbours rather
# than its content.
STRIP = [
    re.compile(r"\]\([^)]*\)"),        # link targets — See also sections
    re.compile(r"^\s*\|.*\|\s*$", re.M),  # table rows are mostly cross-reference
]

# Shapes the patterns match that are not Kodi symbols: SQL, log severities, HTTP,
# and the file names this repo talks about constantly. Two skills sharing SELECT
# tells you they both contain SQL, which is not a finding.
STOPWORDS = {
    "SELECT", "WHERE", "UPDATE", "INSERT", "DELETE", "ORDER", "GROUP", "LIMIT",
    "PRAGMA", "CREATE", "TABLE", "INDEX", "COMMIT", "BEGIN", "NULL", "COUNT",
    "ERROR", "DEBUG", "WARNING", "FATAL", "INFO", "NOTICE", "TRACE",
    "HTTP", "HTTPS", "JSON", "HTML", "POST", "SKILL", "CLAUDE", "README",
    "CONTRIBUTING", "LICENSE", "TODO", "NOTE", "STOP", "YAML", "UTF",
}


def tokens(path: Path) -> set[str]:
    text = FRONTMATTER_RE.sub("", path.read_text(encoding="utf-8"))
    for pattern in STRIP:
        text = pattern.sub(" ", text)
    found: set[str] = set()
    for pattern in PATTERNS:
        found.update(m.group(0).rstrip(".:") for m in pattern.finditer(text))
    # `std::` names are C++ vocabulary. Two skills both containing a vector is
    # not a relationship between them.
    found = {t for t in found
             if len(t) > 3 and t not in STOPWORDS and not t.startswith("std::")}

    # `std::shared_ptr` and `shared_ptr` are one symbol counted twice, which
    # inflates every pair that mentions it. Keep the qualified form only.
    qualified = {t.rsplit("::", 1)[-1] for t in found if "::" in t}
    return found - qualified


def skill_paths() -> list[Path]:
    return sorted(p for d in SKILL_DIRS for p in (REPO / d).rglob("SKILL.md"))


def label(path: Path) -> str:
    return str(path.parent.relative_to(REPO))


def build_corpus() -> tuple[dict[str, set[str]], dict[str, float]]:
    fingerprints = {label(p): tokens(p) for p in skill_paths()}
    n = len(fingerprints)
    df = Counter(t for fp in fingerprints.values() for t in fp)
    weights = {
        t: math.log(n / count)
        for t, count in df.items()
        if count / n <= MAX_DOC_FRACTION
    }
    return fingerprints, weights


def score(a: set[str], b: set[str], weights: dict[str, float]) -> tuple[float, list[str]]:
    shared = [t for t in a & b if t in weights]
    total = sum(weights[t] for t in shared)
    shared.sort(key=lambda t: -weights[t])
    return total, shared


def report(pairs, markdown: bool, top: int) -> None:
    if not pairs:
        print("no overlapping pairs above the threshold")
        return
    if markdown:
        print("### Possible overlap\n")
        print("These share distinctive symbols. Overlap is not automatically a")
        print("problem — check whether it is duplication or a cross-reference.\n")
        print("| Score | Skills | Shared symbols |")
        print("|---|---|---|")
        for total, x, y, shared in pairs[:top]:
            syms = ", ".join(f"`{t}`" for t in shared[:6])
            print(f"| {total:.1f} | `{x}` · `{y}` | {syms} |")
        return
    for total, x, y, shared in pairs[:top]:
        print(f"{total:5.1f}  {x}  <->  {y}")
        print(f"       {', '.join(shared[:8])}")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--against", nargs="*", type=Path, metavar="SKILL.md",
                    help="report nearest neighbours of these files only")
    ap.add_argument("--top", type=int, default=15, help="pairs to print (default 15)")
    ap.add_argument("--markdown", action="store_true",
                    help="emit a markdown table, for a CI step summary")
    args = ap.parse_args()

    fingerprints, weights = build_corpus()
    if len(fingerprints) < 2:
        print("fewer than two skills — nothing to compare")
        return 0

    pairs: list[tuple[float, str, str, list[str]]] = []

    if args.against:
        targets = []
        for p in args.against:
            key = label(p.resolve())
            if key not in fingerprints:
                print(f"warning: {p} is not a skill in this repo", file=sys.stderr)
                continue
            targets.append(key)
        for key in targets:
            for other, fp in fingerprints.items():
                if other == key or other in targets and other < key:
                    continue
                total, shared = score(fingerprints[key], fp, weights)
                if total >= MIN_SCORE:
                    pairs.append((total, key, other, shared))
    else:
        names = sorted(fingerprints)
        for i, x in enumerate(names):
            for y in names[i + 1:]:
                total, shared = score(fingerprints[x], fingerprints[y], weights)
                if total >= MIN_SCORE:
                    pairs.append((total, x, y, shared))

    pairs.sort(key=lambda r: -r[0])
    report(pairs, args.markdown, args.top)

    # Informational by design. A high score is a question, not a defect, and a
    # check that fails on a question trains people to route around it.
    return 0


if __name__ == "__main__":
    sys.exit(main())
