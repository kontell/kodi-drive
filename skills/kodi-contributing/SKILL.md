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
  verified:
    kodi: ["22 master"]
    platform: ["Linux x86_64"]
    date: "2026-08-13"
    method: sourced
---

# Contributing upstream

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
