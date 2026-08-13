# Contributing to kodi-drive

Most contributions here come from coding agents finishing a session. This document is written to be read
by one. If you are a human, everything below applies to you too — you will just find the tone unusually
blunt.

---

## The bar: only what you verified

Every future agent that reads a skill will trust it completely. It has no way to check. That asymmetry is
the whole reason this bar exists, and why it is higher than a normal documentation repo's.

**A wrong skill is worse than no skill.** No skill costs an agent an hour of rediscovery. A wrong skill
costs it an hour of rediscovery *plus* however long it spends trusting the wrong thing first — and it
propagates, because the next contributor builds on it.

So: **every claim in a skill must be one of three things.**

| Tier | What it means | What you must be able to show |
|---|---|---|
| `observed` | You ran it against a live Kodi and saw the result | The exact command, and its actual output |
| `sourced` | It is traceable to Kodi's source, an add-on's source, or official docs | `xbmc/Application.cpp:1234`, or a docs URL |
| `inferred` | It follows logically from something above, **and you labelled it as such** | The premises it follows from |

If a claim is none of these, it does not go in a skill.

### It goes in an issue instead — and that is a real contribution

Open an [Unverified observation](../../issues/new?template=unverified-observation.yml) issue. Say what you
saw, what you could not confirm, and what would settle it.

This is genuinely useful and we want it. "I saw X twice on Kodi 21 but could not reproduce on 22" is
valuable information. Laundering it into a skill as "X happens on Kodi 21" is not — it is a guess wearing
a fact's clothes, and someone will act on it.

### Uncertainty has a home inside skills too

A skill may carry an `## Open questions` section. Anything under that heading is exempt from the
confidence rules — it is explicitly marked as not-yet-known, so it cannot mislead. Use it. The failure
mode we are guarding against is not "the agent was unsure", it is "the agent was unsure and hid it."

### What CI will reject

`scripts/validate.py` runs on every PR and fails on:

- Missing or malformed frontmatter, or a missing `metadata.verified` block.
- **Hedging language** outside an `## Open questions` section: `probably`, `should work`, `I think`,
  `might be`, `seems to`, `presumably`, `in theory`, `likely`, `may need to`, `appears to`, `I believe`.
  If you find yourself reaching for one of these, you have found an issue, not a skill.
- A skill body over ~500 lines — split it (see [Skills are small](#skills-are-small)).

Run it yourself before opening the PR:

```sh
python3 scripts/validate.py
python3 scripts/scrub.py --detect
```

---

## Privacy and security

**Nothing in this repo may identify a person, a machine, or a network.**

Not because the maintainers are fussy, but because this content is harvested from real debugging sessions,
and real debugging sessions are saturated with hostnames, tokens, and IP addresses. One careless paste
publishes someone's home network.

Never commit:

- Hostnames, IP addresses (other than loopback and the RFC 5737 documentation ranges), MAC addresses
- ADB serials or `host:port` pairs, SSH targets, SMB/NFS paths
- API keys, tokens, JWTs, passwords, session ids, or any URL carrying them as a query parameter
- Usernames, home directory paths, email addresses
- Media library contents — titles, counts, and watch history fingerprint a household surprisingly well

Use placeholders instead. They are conventional, and readers understand them:

`<KODI_HOST>` · `<KODI_PORT>` · `<ADB_SERIAL>` · `<SERVER_URL>` · `<USER>` · `<API_KEY>`

Or refer to `$KODI_TARGET` and let [`bin/`](bin/) resolve it.

### Two things that catch people out

**Kodi logs credentials at debug level.** Kodi core and `inputstream.adaptive` write full stream URLs —
including `api_key=` and `token=` query parameters — to `kodi.log` at debug level, and an add-on cannot
prevent this. **Any log excerpt you paste is credential-bearing until proven otherwise.** Redact before
pasting, not after.

**Agent transcripts record everything you print.** If you `cat` a credentials file, that value is now in a
session transcript on disk, and transcripts are not scrubbed. Read credentials into environment variables;
never echo them.

### The tooling

```sh
python3 scripts/scrub.py --detect          # fail on anything that looks private
python3 scripts/scrub.py --redact FILE...  # apply your local mapping to migrated content
```

`--redact` uses `.scrub-map.local` (gitignored) to replace known private strings with stable placeholders.
Stable matters: the same host becomes the same placeholder everywhere, so migrated prose stays readable.
Create it from `.scrub-map.example`.

CI runs `--detect` plus `gitleaks` independently. Both must pass.

---

## Before you add a skill: is it already here?

Duplication is the failure mode this repo is most likely to die of. Two skills that half-cover the same
thing are worse than one that covers it fully, because now a reader has to find both and reconcile them.

**In your PR description, you must list the three existing skills closest to what you are adding, and say
why this is not an edit to one of them.** If you cannot name three, you have not looked.

```sh
grep -ril "<the key term>" skills/ addons/ adjacent/
```

Editing an existing skill is the better contribution more often than people expect. A skill that gains a
verified caveat is more valuable than a new skill that restates it in a different order.

---

## Skills are small

One topic per skill. If you cannot state what a skill covers in one sentence without "and", it is two
skills.

Small skills are not a style preference — they are the mechanism. An agent loads a skill body only when it
needs it, so a 200-line skill on exactly the right topic costs almost nothing, while a 900-line
everything-skill costs a lot and gets loaded for the wrong reasons.

Target 50–250 lines. Over ~500 and CI will tell you to split.

Put long reference material — tables, enumerations, generated output — in a sibling file
(`skills/<name>/reference.md`) and link to it. It loads only if the agent follows the link.

---

## Writing a skill

```sh
scripts/new-skill.sh kodi-thing-you-learned
```

That scaffolds `skills/kodi-thing-you-learned/SKILL.md` from the template. Frontmatter:

```yaml
---
name: kodi-texture-cache
description: >
  How Kodi's texture cache decides whether to re-encode, and why an RGBA source costs
  you twice. Use when add-on artwork is slow to load, cached images look wrong, or you
  are choosing an image format to serve to Kodi.
license: CC-BY-SA-4.0
metadata:
  category: diagnosis
  verified-kodi: "21.3 Omega, 22.0b1 Piers"
  verified-platform: "Linux x86_64, Android TV"
  verified-date: "2026-08-13"
  verified-method: observed
---
```

`description` is the only part an agent sees before deciding to load the skill, so it does double duty:
**what this is**, then **when to reach for it**. Lead with the use case. Agents match on the trigger, not
on the topic.

The [Agent Skills spec](https://agentskills.io/specification) permits only **string values** in
`metadata`, so these are flat keys with comma-separated lists rather than a nested block.
`validate.py` rejects anything else.

- `category` — groups the skill in [the catalogue](skills/README.md). Run `validate.py` against a bad
  value to see the accepted set.
- `verified-kodi` — every version you actually tested. Not "21+". If you only tested Omega, say only Omega.
- `verified-platform` — Linux, Windows, macOS, Android TV, and so on. Behaviour genuinely diverges.
- `verified-date` — when you verified it. `validate.py` warns past ~12 months.
- `verified-method` — `observed`, `sourced`, or `inferred`, matching the tiers above. If a skill mixes
  tiers, use the weakest one here and label the individual claims in the body.

### Style

Write for an agent that will act on this immediately, in a hurry, without checking.

- **State the behaviour, then the consequence.** "A malformed include is dropped silently — Kodi logs a
  parse error and renders the window without it, so a missing element is a parse failure until proven
  otherwise."
- **Say what fails silently.** Silent failures are the highest-value content in the whole repo, because
  they are exactly what an agent cannot discover by looking.
- **Give the command, not a description of the command.** Copy-pasteable, with placeholders.
- **Include the numbers if you measured them.** "0.62 s → 0.17 s" beats "faster" and is checkable.
- **Name Kodi versions when behaviour differs.** "Omega refuses, Piers sniffs" is the useful form.
- Prefer short paragraphs over deep bullet nesting. Agents parse prose fine; deep nesting loses structure.

---

## Add-on policy

We follow Kodi's own rules — [Add-on rules](https://kodi.wiki/view/Add-on_rules),
[Submitting Add-ons](https://kodi.wiki/view/Submitting_Add-ons), and the
[Forum rules / Banned add-ons](https://kodi.wiki/view/Official:Forum_rules/Banned_add-ons) list.

**Not accepted:** skills about add-ons whose purpose is accessing infringing content; "builds", wizards,
and the repositories and forks on Kodi's banned list; anything circumventing DRM.

**Explicitly accepted**, because it is a common misconception: **scraping a public website to build an
unofficial add-on is not piracy.** Unofficial, unlisted, and reverse-engineered add-ons are all welcome
here. The line is the content, not the distribution channel.

If you are unsure which side of the line something is on, open an issue and ask before writing it.

---

## Pull requests

Branch, commit, open a PR against `main`. The
[PR template](.github/PULL_REQUEST_TEMPLATE.md) asks you to fill in evidence per claim — **fill it, do not
tick it.** An empty evidence block is the signal that a claim is not ready, and it is visible to a
reviewer in a way an unticked box is not.

For agents finishing a session, `/kodi-drive:contribute` does the whole flow: collects what was learned,
checks it for overlap against existing skills, scrubs it, and opens the PR with evidence filled from the
actual session.

Commits: imperative subject, and say *why* in the body when the why is not obvious. The commit histories
this repo was built from are full of one-line fixes whose reasoning took an hour to rediscover.

---

## Licence

Contributions to prose and skills are under [CC BY-SA 4.0](LICENSE); `bin/` and `scripts/` are
GPL-2.0-or-later. By opening a PR you agree your contribution ships under those terms.
