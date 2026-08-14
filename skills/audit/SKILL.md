---
name: audit
description: >
  Sweep kodi-drive for the decay that per-PR checks cannot catch — duplicate
  coverage, claims verified against a Kodi nobody runs any more, skills nothing
  links to, and defects recorded but never filed upstream. Use periodically, when
  a new Kodi major ships, or when a contribution feels like it might already be
  here. Covers the mechanical overlap check and how to tell real duplication from
  a legitimate cross-reference.
license: CC-BY-SA-4.0
metadata:
  category: workflow
  verified-date: "2026-08-14"
  verified-method: observed
---

# Auditing the repo

Every check in CI runs on a **diff**. That catches a bad addition and nothing
else. The failure modes that actually threaten a knowledge repo are slower: two
skills drifting into the same territory, a verified claim quietly ageing out, a
skill nobody links to any more.

None of those fail. That is the problem — the repo just gets worse, and the first
symptom is a contributor who cannot find the thing that was already here.

Run the five sweeps below. They take a few minutes together.

## 1. Duplication

```sh
python3 scripts/overlap.py            # every pair, ranked
python3 scripts/overlap.py --top 25
```

It fingerprints each skill by the identifiers in its body — `CJobManager`,
`Player.SetTempo`, `special://`, `INPUTSTREAM_SUPPORTS_IDISPLAYTIME` — weighted
by rarity across the repo. Prose about Kodi is generic; the symbols are not.

**Read the shared symbols, not the score.** A high score between two skills that
*should* both mention a class is expected — `kodi-known-defects` names the
classes half the diagnosis skills cover, and that is the point of it.

The discriminator:

| Signal | Reading |
|---|---|
| The same **code block** in two skills | duplication — one copy will get fixed and the other will not |
| The same **claim**, worded differently | duplication — a reader now has to reconcile two versions |
| The same **class or method** named for different purposes | cross-reference, leave it |
| Only C++ or SQL vocabulary in common | noise |

### Resolving one

**One skill owns the detail; the other links to it.** Pick the owner by asking
which skill a reader arrives at with this question — not which one is longer.

A defect record and a how-to-avoid-it both legitimately mention the same symbol.
The defect record owns the reproduction and the upstream status; the how-to owns
the guidance. Neither needs the other's half.

Merging two skills outright is the right answer only when neither can state its
topic without the other's content.

## 2. Staleness

```sh
python3 scripts/validate.py --strict
```

`--strict` promotes warnings to failures, which is what surfaces the ageing.
Two warnings matter here:

- **`last verified N days ago`** — past `STALE_DAYS` (400, so a yearly
  re-verification does not trip it).
- **`not verified against current stable Kodi`** — the skill's `verified-kodi`
  omits the current stable major.

Re-verify against a live Kodi and bump `verified-date`, or move the uncertain
part under `## Open questions`, which is exempt from the confidence rules.
**Bumping the date without re-running anything is the one thing that must not
happen** — it converts a stale claim into a fresh-looking one.

### When a new Kodi major ships

Bump `CURRENT_STABLE_MAJOR` in `scripts/validate.py`, then run `--strict` and
read what lights up. That is the re-verification worklist for the release, and it
is the only time the whole repo needs revisiting at once.

## 3. Skills nothing links to

```sh
for d in skills/*/ adjacent/*/ addons/*/; do
  [ -f "$d/SKILL.md" ] || continue
  n=$(basename "$d")
  c=$(grep -rl --include='SKILL.md' "$n/SKILL.md" skills adjacent addons 2>/dev/null \
      | grep -cv "^${d%/}/")
  [ "$c" -eq 0 ] && echo "unlinked: $n"
done
```

Exclude the catalogue deliberately — `skills/README.md` is generated and links
every skill, so including it makes the check incapable of firing.

**An entry-point skill can appear here legitimately** — one reached from the
README rather than from a sibling is unlinked by this measure and still perfectly
reachable. Everything else in the list means a reader following the skills will
never arrive there.

This sweep found two genuine orphans on the run that produced this skill:
`jellyfin-client` and `kodi-idle-screensaver`, both fixed by adding them to
`kodi-orientation`'s map.

An unlinked skill is not free. The Agent Skills spec loads every skill's name and
description at startup, for every session, used or not — Claude Code's own
accounting puts this repo's skills at roughly 130–170 tokens each. A skill
nobody can reach is a permanent tax on every agent that installs the plugin.

Fix it by linking from the skill a reader actually starts at, usually
`kodi-orientation`'s map or a sibling's `## See also`. Delete it if it turns out
nothing points there because nothing needs it.

## 4. Size drift

`validate.py` warns above 300 lines and fails above 500. A skill that has grown
past the warning has usually acquired a second topic rather than more detail on
its first.

```sh
wc -l skills/*/SKILL.md addons/*/SKILL.md adjacent/*/SKILL.md | sort -rn | head
```

Split by topic, or move tables and enumerations into a sibling
`reference.md` — a linked file loads only if the agent follows the link, so the
cost of long reference material drops to zero for everyone who does not need it.

## 5. Defects recorded but never filed

```sh
awk '/^## /{h=$0} /Status: `unreported`/{print h}' skills/kodi-known-defects/SKILL.md
```

An entry sitting at `unreported` helps whoever reads the skill and nobody else.
Filing it upstream is what stops the next person hitting it at all. Check each
against the [xbmc issue tracker](https://github.com/xbmc/xbmc/issues) before
filing — someone else may have got there since.

Update the status vocabulary in the skill as each moves: `unreported` → `filed` →
`pr-open` → `merged`.

## On a pull request

The same overlap check, scoped to what the PR adds:

```sh
python3 scripts/overlap.py --against skills/<new-skill>/SKILL.md
python3 scripts/overlap.py --markdown --top 10   # as a CI step summary
```

CI runs this and writes the table to the job summary **without failing the
build**. A high score is a question, not a defect, and a check that fails on a
question trains contributors to route around it.

## What fails silently

- **All of it.** That is the defining property of this list — every item here
  passes every automated check the repo has. The repo degrades without ever going
  red.
- **A duplicate that gets fixed in one copy only.** The two then disagree, and a
  reader has no way to tell which is current.
- **A bumped `verified-date` with no re-verification.** Indistinguishable from a
  real re-check, and it resets the staleness clock for another 400 days.

## Open questions

- The overlap threshold (`MIN_SCORE = 3.0`) was calibrated against this repo at
  roughly forty skills. Whether it stays useful at two hundred has not been
  tested — if the report becomes noise, raise it rather than ignoring the report.

## See also

- [`contribute`](../contribute/SKILL.md) — the per-session loop, which runs the
  same overlap check on one skill before it lands
- [CONTRIBUTING](../../CONTRIBUTING.md) — the bar each of these sweeps is
  protecting
- [`kodi-known-defects`](../kodi-known-defects/SKILL.md) — the sweep-5 worklist
