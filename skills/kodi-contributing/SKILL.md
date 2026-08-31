---
name: kodi-contributing
description: >
  Get a change accepted into Kodi itself, or an add-on into the official
  repository. Use when opening a PR against xbmc/xbmc or an xbmc add-on repo, when
  a PR build is failing on formatting, or when preparing an add-on for submission.
  Covers what the CI actually enforces per commit, and what the @kodiai review bot
  will flag before a human looks.
license: CC-BY-SA-4.0
metadata:
  category: shipping
  verified-kodi: "22 master"
  verified-platform: "Linux x86_64"
  verified-date: "2026-08-31"
  verified-method: "observed"
---

# Contributing upstream

## Kodi has an AGENTS.md, and it is about you

Since [#29081](https://github.com/xbmc/xbmc/pull/29081) (merged 2026-08-31) the
repository root carries an
[`AGENTS.md`](https://github.com/xbmc/xbmc/blob/master/AGENTS.md), with a
`CLAUDE.md` that is nothing but `@AGENTS.md`. **Read it before writing code, not
before opening the PR.**

It is deliberately narrow so far — it covers code comments only — and the team
has said it will grow as their AI policy settles. Do not assume the scope you
last saw is the current one.

The current rules amount to: comments explain what the code cannot, and nothing
else. No restating the code. No mentioning approaches tried, considered,
replaced or removed. Nothing that only makes sense as a trace of how an agent
arrived at the result. Prefer deleting a comment over rewording it. History,
discarded alternatives and review rationale belong in the commit message or the
PR description.

**Comments are what their maintainers object to in agent-written PRs**, and that
is why the file exists: the PR that added it states the team is varied on AI use
but universally agrees AI comments are terrible, and calls this their most
pressing concern.

A mirror is kept at [`docs/upstream/xbmc-AGENTS.md`](../../docs/upstream/xbmc-AGENTS.md)
for offline use, with the upstream commit it was taken from. It is a snapshot
and the canonical file is upstream; `scripts/sync-upstream-docs.py` reports
drift and CI runs it weekly.

## Kodi itself: what the CI enforces

Read [`docs/CONTRIBUTING.md`](https://github.com/xbmc/xbmc/blob/master/docs/CONTRIBUTING.md)
and [`docs/CODE_GUIDELINES.md`](https://github.com/xbmc/xbmc/blob/master/docs/CODE_GUIDELINES.md)
— this skill does not restate them. Two points are worth calling out because they
catch people out mechanically rather than editorially:

**Every individual commit must satisfy `.clang-format`, not just the final tree.**
The PR build job checks each commit separately. A series that formats correctly at
the tip but not at commit 2 of 5 will fail.

The consequence is counter-intuitive: if your change touches existing code that
needs reformatting under the current rules, that reformatting is a **related
cosmetic change belonging in the same commit** — despite the general rule that
code and cosmetics stay separate.

**Squash and organise before submitting.** Kodi wants a coherent history of
meaningful commits, not a record of how you got there.

The [PR template](https://github.com/xbmc/xbmc/blob/master/docs/PULL_REQUEST_TEMPLATE.md)
asks for description, motivation and context, **how it was tested** (with your
testing environment), and the effect on users — that last section may be used to
generate release notes, so write it for a user rather than a reviewer.

## `@kodiai` will review before a human does

Kodi runs [`xbmc/kodiai`](https://github.com/xbmc/kodiai), a GitHub App that
auto-reviews PRs across the xbmc repositories, responds to `@kodiai` mentions,
and triages issues. Expect a machine review on your PR.

Knowing what it is doing makes it easier to work with:

- It retrieves over Kodi's **code, the wiki, past review comments, issues, and
  merged diffs**, so it comments with project precedent rather than generic
  advice. If it cites a prior review, that is a real prior review.
- It applies **epistemic guardrails** — a claim it cannot ground in the diff or
  retrieved context is dropped rather than hedged. So its findings are terse by
  design, and an absent comment is not an endorsement.
- On **add-on repositories** it runs a dedicated add-on-rule review against
  Kodi's [Add-on rules](https://kodi.wiki/view/Add-on_rules), mixing deterministic
  checks with model-backed ones.

Two practical consequences. **Fix the deterministic things before you open the
PR** — missing English description in `addon.xml`, missing licence file — because
they will be flagged and cost a round trip. And **you can ask it directly**:
`@kodiai review` requests a re-review, and it answers questions in comments.

## Add-ons: the official repository

Submissions go to the official repo on GitHub as pull requests, and the mechanics
are strict:

- **One commit per PR**, with the message formatted `[addonid] version`.
- Only PRs **from the add-on author or their successor** are accepted.
- **Python 3 only.** Python 2 contributions are no longer accepted.
- **A licence file is required** — `LICENSE.txt`. CC-BY-SA-3.0 is recommended for
  skins, GPL-2.0-or-later for everything else; most copyleft licences are
  acceptable.
- **All files must be free and legal to distribute**, and the add-on must not
  violate copyright.
- **Monetisation is not allowed**, unless you own the copyright in the content
  the add-on provides.

Full detail: [Submitting Add-ons](https://kodi.wiki/view/Submitting_Add-ons) and
[Add-on rules](https://kodi.wiki/view/Add-on_rules).

## Before you file a Kodi bug

Two things save a maintainer's time and make the report actionable:

**Rule out add-ons first.** Reproduce in a clean profile — see
[`kodi-clean-profile`](../kodi-clean-profile/SKILL.md). A report that already says
"reproduces with no add-ons installed" is worth far more than one that does not.

**Attach a debug log captured with logging on *before* the reproduction**, and
[redact it](../kodi-logs/SKILL.md). Kodi and `inputstream.adaptive` write full
stream URLs including `api_key=` at debug level, so an unredacted log posted to a
public issue publishes your credentials.

And check [`kodi-known-defects`](../kodi-known-defects/SKILL.md) first — the bug
may already be filed.

## Search the tracker before you invest, not after

Search **as soon as you have a mechanism**, before writing the report, before
writing a fix, and long before building anything. A defect worth finding is
often a defect someone else has already found.

```sh
gh search issues --repo xbmc/xbmc --include-prs --limit 10 "<distinctive symbol>"
```

Search on symbols, not symptoms: a function or member name from the stack —
`RegisterSettingsLoadedCallback`, `MHD_stop_daemon` — finds the thread that
matters, where "kodi hangs on profile switch" finds nothing.

**`--include-prs` is not optional.** The fix can be sitting in an open PR while
the issue is still open and misdiagnosed, and a search that returns issues only
tells you the defect is unreported when it is a day from merging.

**The trap: `--state all` is invalid.** `gh` accepts only `{open|closed}` there,
and rejects the command:

```
invalid argument "all" for "--state" flag: valid values are {open|closed}
```

Omit `--state` entirely to search both. With `2>/dev/null` in the pipeline —
which is how it usually gets written — the rejection is swallowed and the empty
output reads exactly like "no results".

Read the open PRs that touch the file, not only the ones whose titles match. A
fix often arrives inside a PR opened for something else entirely, added in
response to review.

## Writing for upstream, on someone's behalf

Almost everything an agent publishes upstream is posted under a human's account.
Four rules follow from that, and the first two are not stylistic.

**Do not ghost-write.** Never put a first-person claim of experience into the
human's voice — "I hit this on my Bravia", "I rebuilt it and the crash is gone".
The agent did not, and the human cannot defend the detail when a reviewer asks
which build, which device, what else was running. Attribute to the evidence
instead: *"this reproduces on a 22.0-BETA1 Android TV box"*, *"a core dump taken
from a separate reproduction shows"*. That reads as more careful rather than
less, because it says exactly what is being claimed. The failure is silent — no
reader can tell a fabricated first-person detail from a real one, so the whole
report stops being trusted at once rather than one line of it.

**Sign as a bot by default.** One line at the top: *"This comment was written by
Claude and posted by @user."* This is already the local norm — xbmc threads
carry both that form and `<!-- AI-generated using ... -->` disclosures. Sign by
default and let the human remove it, because the reverse is unrecoverable: being
found out costs their credibility on every thread they have posted to. It also
tells a maintainer how much scrutiny the text has had before they spend review
time on it.

**Be concise.** State the mechanism once and refer back to it, rather than
re-explaining it under the fix and again in the summary. Cut the reasoning you
needed to convince yourself; a maintainer triaging fifty issues reads the first
screen, and length reads as noise rather than thoroughness.

**Leave out irrelevant history.** Do not narrate the investigation — what was
tried first, the tool that did not work, the theory abandoned. This is the same
rule Kodi applies to code comments in
[`AGENTS.md`](https://github.com/xbmc/xbmc/blob/master/AGENTS.md), and it is
what their maintainers are most vocal about, so it is worth internalising rather
than working around.

The exception is where that rule gets misapplied: **a negative result the reader
would otherwise repeat is a finding, not history.** *"Offline gdb resolves
nothing against a Flatpak core"* saves the next person an hour and belongs in
the write-up. *"I first tried offline gdb"* is about you and belongs nowhere.
The test is whether the reader is about to make the same mistake.

## What fails silently

- A PR series that formats correctly only at the tip passes local checks and
  fails CI.
- An add-on PR from someone other than the author is closed regardless of quality.
- An unredacted debug log on a public issue is a credential disclosure that looks
  like helpfulness.

## Open questions

- Whether `@kodiai`'s add-on-rule review runs on the official add-on repository
  itself or only on individual add-on repos has not been confirmed from outside.
- Kodi's requirements change. Everything above is a pointer to the canonical
  documents rather than a substitute — re-read them before a first submission.

## See also

- [`kodi-versions-abi`](../kodi-versions-abi/SKILL.md) — which Kodi versions your
  add-on will install on
- [`kodi-addon-release`](../kodi-addon-release/SKILL.md) — building the artifact
- [`kodi-known-defects`](../kodi-known-defects/SKILL.md) — check before filing
