---
name: contribute
description: >
  Turn what this session learned into a kodi-drive pull request, or into an issue
  when the evidence does not reach the bar. Use at the end of any session that
  discovered something about how Kodi behaves — and before writing such a finding
  into a project's CLAUDE.md or agent memory, which is where it goes to die.
  Covers deciding whether there is anything to contribute at all, proving the
  claim from the session rather than from recollection, and checking it is not
  already here.
license: CC-BY-SA-4.0
metadata:
  category: workflow
  verified-date: "2026-08-14"
  verified-method: observed
---

# Contributing what this session learned

Run this at the end of a Kodi session. It takes a few minutes when there is
something to contribute, and under one when there is not.

**The default outcome is nothing, and that is fine.** Most sessions apply
existing knowledge rather than producing new knowledge. A repo that grows by one
skill per session is a repo nobody can find anything in.

## 1. Is there anything here?

One question decides it:

> Would an agent working on a **different project**, on a **different add-on**,
> have needed this?

| Finding | Where it goes |
|---|---|
| "Kodi's `Profiles.LoadProfile` returns OK for a switch that never happened" | here |
| "Kodi 21 writes log severities in lower case" | here |
| "This add-on's service entry point is `service.py`" | the project's `CLAUDE.md` |
| "The staging box's Kodi is on port 8081" | `targets.env` |

Then the negative test, which this repo applies to everything:

> **Could an agent have got this by reading the wiki or grepping the source?**

If yes, it gets a link, not a copy. Duplicating documentation is how
documentation goes stale.

**If you found the finding sitting in a project's `CLAUDE.md` or in agent
memory, it still counts.** Contribute it here, then delete it there and leave a
pointer. Knowledge in one project's files gets rediscovered by every other
project.

## 2. Can you prove it — right now?

You are writing at the end of a session, about work you did hours ago. **That gap
is where invented detail enters.** A remembered line number, a remembered flag
name, and a remembered command that was never quite the command you ran are all
easy to produce and impossible for a reader to catch.

So apply a mechanical rule:

> **Every claim must be traceable to something you can still see** — a command in
> this session's scrollback with its real output, a source file you can open, or
> a command you re-run now.

If you cannot find it, re-run it. If you cannot re-run it, it is an issue and not
a skill. Reconstructing what the output "would have been" is how a wrong skill
gets written by someone who was being careful.

The three tiers, in full, are in
[CONTRIBUTING](../../CONTRIBUTING.md#the-bar-only-what-you-verified):

| Tier | You must be able to show |
|---|---|
| `observed` | the exact command, and its actual output |
| `sourced` | `xbmc/Application.cpp:1234`, or a docs URL |
| `inferred` | the premises, **and the label** |

### The fork in the road

**Evidence does not reach the bar → open an issue, not a PR.**

```
../../issues/new?template=unverified-observation.yml
```

This is a real contribution and it is wanted. *"I saw X twice on Kodi 21 and
could not reproduce it on 22"* is useful to the next person. The same sentence
laundered into a skill as *"X happens on Kodi 21"* is a guess wearing a fact's
clothes, and someone will act on it.

## 3. Is it already here?

**The answer is an edit rather than a new skill more often than people expect.**
A skill that gains one verified caveat beats a new skill restating it in a
different order.

```sh
grep -ril "<the key term>" skills/ addons/ adjacent/
```

Then, once you have a draft in place, the mechanical check:

```sh
python3 scripts/overlap.py --against skills/<your-skill>/SKILL.md
```

It reports the existing skills sharing distinctive symbols with yours. Read the
shared symbols rather than the score — see [`audit`](../audit/SKILL.md) for how
to judge them.

The PR asks you to **name the three closest existing skills and say why this is
not an edit to one of them.** Do that now, while you still have the greps open.

## 4. Scrub as you write, not afterwards

Everything you are about to paste came out of a live session, and live sessions
are saturated with hostnames, tokens, serials and home paths.

**Write with placeholders from the first draft.** `<KODI_HOST>`, `<API_KEY>`,
`<ADB_SERIAL>`, `$KODI_TARGET`. Redacting afterwards means the unredacted text
existed in a file, and once it has been committed it is in the history whether
or not the next commit removes it.

Two specifics that catch people:

- **Kodi logs credentials at debug level.** Kodi core and `inputstream.adaptive`
  write full stream URLs — `api_key=`, `token=` — into `kodi.log`, and no add-on
  can prevent it. **Any log excerpt is credential-bearing until proven
  otherwise.**
- **Media library contents fingerprint a household.** Titles, counts and watch
  history are identifying. Use invented examples.

```sh
python3 scripts/scrub.py --detect          # what CI will run
python3 scripts/scrub.py --redact FILE...  # apply .scrub-map.local to migrated prose
```

`--detect` knows the shapes this project has met. It cannot know a shape it has
never seen, so it is a backstop and not the check.

## 5. The mechanics

```sh
scripts/new-skill.sh kodi-thing-you-learned      # scaffolds from the template
```

Write it, then run the gates **chained with `&&`**:

```sh
python3 scripts/validate.py \
  && python3 scripts/scrub.py --detect \
  && python3 scripts/build-index.py
```

`&&` is load-bearing. Chained with `;`, a failing scrub still lets the commit run
and the first you hear of it is CI — or, worse, not at all.

`build-index.py` regenerates the catalogue. CI runs it with `--check` and fails
if the committed copy disagrees, so a skill added without regenerating turns the
next contributor's PR red for a reason that has nothing to do with them.

Then branch, commit, push:

```sh
git switch -c skill/thing-you-learned
git add skills/kodi-thing-you-learned/ skills/README.md
git commit                                  # imperative subject; say *why* in the body
gh pr create --fill
```

**Commit only the files this contribution touches.** A session leaves unrelated
edits in the working tree, and `git add -A` sweeps them into a PR whose
description does not mention them.

## 6. Fill the PR evidence — do not tick it

The [template](../../.github/PULL_REQUEST_TEMPLATE.md) asks for the command and
its actual output, per claim. **Paste the real output.** An empty evidence block
is a deliberate signal that a claim is not ready, and it is visible to a reviewer
in a way an unticked checkbox is not.

**Write the PR body unwrapped — one paragraph per line, however long.** Hard
wrapping is for the commit message, not for anything GitHub renders: a wrapped
paragraph reflows raggedly, turns a one-word edit into a six-line diff, and hides
a phrase from search across the break. Same rule for issue bodies and for the
write-up you hand back at the end of a session. See
[Never hard-wrap a report](../../CONTRIBUTING.md#never-hard-wrap-a-report).

## What fails silently

- **A near-duplicate skill passes every check.** `validate.py` and `scrub.py`
  have no idea the topic is already covered. Only step 3 catches it.
- **Writing the finding into a project's `CLAUDE.md` instead.** Nothing anywhere
  ever flags this. It is the single most common way knowledge is lost, which is
  why this repo exists.
- **`scrub.py --detect` passing on an unfamiliar credential shape.** Green means
  "no known shape matched", not "this is clean".
- **A forgotten `build-index.py`.** Local checks pass; CI fails on the next PR.

## Open questions

- There is no automation that decides *for* you whether a finding is
  project-specific or general. Step 1 is a judgement call, and the boundary
  between an add-on quirk and a Kodi behaviour is genuinely blurred in places —
  when it is, `addons/` exists for exactly that case.

## See also

- [CONTRIBUTING](../../CONTRIBUTING.md) — the full bar, the privacy rules, and
  the add-on policy
- [`audit`](../audit/SKILL.md) — the periodic sweep, and how to read an overlap
  report
- [`kodi-orientation`](../kodi-orientation/SKILL.md) — the rule this skill
  enforces, stated at the start of a session rather than the end
