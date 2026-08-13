# kodi-drive

Hard-won Kodi knowledge, packaged so a coding agent can load exactly the piece it needs and nothing else.

Kodi is unusually hostile to reasoning-from-first-principles. A malformed skin include is logged and
dropped rather than raised. A plugin route that forgets to close its handle hangs its caller forever with
no timeout. `<reuselanguageinvoker>` in the wrong element is silently ignored, and nothing is logged either
way. Knowing these costs hours each; re-deriving them costs the same hours again, every session, for every
developer.

This repo is where those hours go so nobody pays them twice.

---

## For agents: how to use this

**Load the skill you need, not this file.** Each skill is a single topic. Their names and one-line
descriptions are already in your context; the bodies load on demand.

If you are running in Claude Code with this repo installed as a plugin, invoke them as
`/kodi-drive:<name>`. Otherwise read `skills/<name>/SKILL.md` directly.

**Start with [`kodi-orientation`](skills/kodi-orientation/SKILL.md)** if you have not worked on Kodi
before. Start with [`kodi-triage`](skills/kodi-triage/SKILL.md) if something is broken and you do not yet
know why.

### Four rules that matter more than any individual skill

**1. Get your hands on a real Kodi. Ask if you do not have one.**
Kodi's behaviour is not reliably derivable from its XML, its docs, or its source. Verify against a running
instance — at planning time, not just at the end. Local, over SSH, over ADB, or via JSON-RPC all work; see
[`kodi-connect`](skills/kodi-connect/SKILL.md).

If you do not have access, **ask the user for it**. Walk them through granting it — that is what
`kodi-connect` is for. Do not quietly degrade to guessing because asking felt like an imposition. A wrong
answer delivered confidently costs everyone more than one question did.

**2. Verify nearly everything by running it.**
"The XML looks right" is not a result. Reload the skin and look. Query JSON-RPC and read the state back.
Take a screenshot. Kodi will disagree with you more often than you expect.

**3. Clone the source of whatever you are interfacing with. Do not work from memory.**
Kodi itself, the add-on you depend on, the server you are talking to. Model recall of a specific API's
behaviour at a specific version is not good enough, and Kodi's version-to-version differences are exactly
where the expensive bugs live.

**4. Credentials go in a file, never in a repo and never in your output.**
API keys, server URLs, and device addresses belong in `~/.config/kodi-drive/targets.env` (mode 0600).
See [Credentials](#credentials). **Never `cat` that file** — agent session transcripts record everything
printed, and they are not scrubbed.

### The rule this repo exists to enforce

> **Broadly-useful Kodi knowledge does not belong in your project's `CLAUDE.md`, `AGENTS.md`, or agent
> memory. It belongs here.**
>
> Project files hold three things: what this project is, its build/test/deploy commands, and its local
> paths. Everything else — how Kodi behaves, what breaks, what the log line means — is knowledge the next
> person needs too, and hoarding it locally is how it gets rediscovered ten times.

When a session teaches you something general, contribute it back before you finish. See
[CONTRIBUTING.md](CONTRIBUTING.md) — but note the bar: **only findings you actually verified.** If you did
not run it, open an issue instead of a pull request. That is a genuinely useful contribution, not a
consolation prize.

---

## Skill index

<!-- BEGIN SKILL INDEX -->

### Skills

*General Kodi knowledge — true across add-ons and installs.*

- [`kodi-adb`](skills/kodi-adb/SKILL.md) — Drive Kodi on Android and Android TV over ADB — screenshots, logs, installing a build, restarting the app, and pulling databases.
- [`kodi-addon-driving`](skills/kodi-addon-driving/SKILL.md) — Install, enable, and exercise a Kodi add-on without navigating menus — fire plugin routes directly, send it service commands, change its settings, and simulate an offline server.
- [`kodi-clean-profile`](skills/kodi-clean-profile/SKILL.md) — Isolate a Kodi problem by reproducing it in a clean profile with no add-ons, then bisect to find the culprit.
- [`kodi-connect`](skills/kodi-connect/SKILL.md) — Find a Kodi on the network and get control of it — JSON-RPC, EventServer, ADB, or SSH — and store its address and credentials safely.
- [`kodi-freeze-diagnosis`](skills/kodi-freeze-diagnosis/SKILL.md) — Work out why Kodi froze, hung, or stopped responding — including getting native backtraces off an unrooted Android TV box.
- [`kodi-jsonrpc`](skills/kodi-jsonrpc/SKILL.md) — Use Kodi's JSON-RPC API as ground truth instead of guessing from screenshots.
- [`kodi-known-defects`](skills/kodi-known-defects/SKILL.md) — Kodi and inputstream.adaptive defects confirmed by investigation, with their symptoms, upstream status, and how to recognise each from a log.
- [`kodi-library-data`](skills/kodi-library-data/SKILL.md) — Kodi's own SQLite databases — where they live, which are per-profile, how to read one safely, and which user-facing operations destroy add-on data.
- [`kodi-logs`](skills/kodi-logs/SKILL.md) — Read kodi.log usefully — turn on debug logging without the on-screen overlay, find the log on any platform, grep for the right severity, and read a crashlog.
- [`kodi-process-control`](skills/kodi-process-control/SKILL.md) — Stop, restart, and measure a Kodi process without killing your own shell or measuring the wrong one.
- [`kodi-profiles`](skills/kodi-profiles/SKILL.md) — Switch Kodi profiles from a script, and enable add-ons in the profile you actually meant.
- [`kodi-screenshot-review`](skills/kodi-screenshot-review/SKILL.md) — Take a Kodi screenshot and actually read it, rather than filing it next to a claim of success.
- [`kodi-test-rig`](skills/kodi-test-rig/SKILL.md) — Stand up a throwaway Kodi an agent can restart, misconfigure, and break.
- [`kodi-triage`](skills/kodi-triage/SKILL.md) — Turn a vague Kodi complaint into a diagnosis.
- [`kodi-ui-navigation`](skills/kodi-ui-navigation/SKILL.md) — Navigate Kodi's UI blind without firing actions at the wrong control.

<!-- END SKILL INDEX -->

Add-on-specific knowledge lives in [`addons/`](addons/); knowledge about non-Kodi systems that Kodi
add-ons commonly talk to lives in [`adjacent/`](adjacent/).

---

## For users: getting the most out of this

**Give your agent a Kodi it can drive.** This is the single biggest difference between a useful session
and a frustrating one. A Kodi the agent can restart, reconfigure, and break is worth more than any amount
of context. Options, roughly in order of usefulness:

- Kodi on the same machine as the agent — best, fastest loop.
- Kodi on your network with the JSON-RPC web server on — good, works from anywhere.
- Android TV or a phone over ADB — good, and the only way to test Android-specific behaviour.
- SSH to the box running Kodi — fine.

**Do not test on the Kodi you actually watch things on.** An agent will restart it, wipe profiles, and
install broken builds. [`kodi-test-rig`](skills/kodi-test-rig/SKILL.md) covers standing up a throwaway
instance; an old Android phone works well and costs nothing.

**Put credentials somewhere the agent can use but not leak.** See below.

**Expect to be asked questions.** A skill that tells the agent to ask for device access is working as
intended. Answering takes a minute; the alternative is a confident wrong answer.

---

## Credentials

Never in a repo. Never in a `CLAUDE.md`. Never echoed into a terminal.

Start from the annotated template:

```sh
mkdir -p ~/.config/kodi-drive && chmod 700 ~/.config/kodi-drive
cp targets.env.example ~/.config/kodi-drive/targets.env
chmod 600 ~/.config/kodi-drive/targets.env
```

Variables are `KODI_<TARGET>_<KEY>`, with the target name upper-cased and hyphens turned into
underscores — target `living-room` becomes `KODI_LIVING_ROOM_*`:

```sh
KODI_TARGET_DEFAULT=devbox

KODI_DEVBOX_HOST=127.0.0.1
KODI_DEVBOX_PORT=8080
KODI_DEVBOX_USER=kodi
KODI_DEVBOX_PASS=changeme

KODI_TV_TRANSPORT=adb
KODI_TV_ADDR=192.0.2.10:5555
KODI_TV_HOST=192.0.2.10
```

Select one per command with `KODI_TARGET=tv kodi-remote home`.

The helpers in [`bin/`](bin/) read this file. Skills refer only to `$KODI_TARGET` and never to a literal
host, so nothing in this repo needs to know your network. You do not have to find the values yourself —
run [`kodi-discover`](skills/kodi-connect/SKILL.md) and it will report what is on your network.

Server credentials for things Kodi talks to — Jellyfin, Emby, Audiobookshelf, an IPTV provider — go in the
same file with the same rules.

---

## Installing

**Claude Code, as a plugin (recommended).** Skills load on demand, and `bin/` lands on your PATH:

```
/plugin marketplace add kontell/kodi-drive
/plugin install kodi-drive
```

**Claude Code, from a clone.** A clone under your skills directory auto-loads with no install step:

```sh
git clone https://github.com/kontell/kodi-drive ~/.claude/skills/kodi-drive
```

Edits to any `SKILL.md` take effect immediately. Run `/reload-plugins` after changing `bin/` or hooks.

**Any other agent.** Skills follow the [Agent Skills](https://agentskills.io) open standard — plain
markdown with YAML frontmatter. Clone the repo and point your tool at `skills/`, or just read the files.

---

## What is in scope

**In:** how Kodi actually behaves, and how to find out. Debugging procedure, live-testing loops, JSON-RPC
and ADB technique, log signatures, skin engine rules, Python and binary add-on patterns, packaging, and
symptom-to-cause maps.

**Out, deliberately:** anything already on the [Kodi wiki](https://kodi.wiki) or readable from the
[Kodi source](https://github.com/xbmc/xbmc). Every skill has to pass *"could an agent have got this by
reading the wiki or grepping the source?"* If yes, it gets a link, not a copy. Duplicating documentation
is how documentation goes stale.

**Also out:** add-ons whose purpose is accessing infringing content, "builds", wizards, and the forks on
Kodi's [banned add-ons list](https://kodi.wiki/view/Official:Forum_rules/Banned_add-ons); anything
circumventing DRM. We follow [Kodi's own add-on rules](https://kodi.wiki/view/Add-on_rules).

To be unambiguous, since it is a common misconception: **scraping a public website to build an unofficial
add-on is not piracy and is entirely welcome here.**

---

## Related work

[`xbmc/kodiai`](https://github.com/xbmc/kodiai) is Team Kodi's own AI integration — a GitHub App doing PR
review and issue triage on the xbmc repos, with retrieval over Kodi's code, wiki, and issue history. It is
complementary to this repo and covers different ground: kodiai reviews contributions *to Kodi*, while
kodi-drive equips an agent working on *your* add-on, skin, or broken install. If you submit an add-on to
the official repository, kodiai is what will review it — [`kodi-contributing`](skills/kodi-contributing/SKILL.md)
covers how to pass.

---

## Licence

Prose and skills: [CC BY-SA 4.0](LICENSE). Scripts in `bin/` and `scripts/`: GPL-2.0-or-later.
See [LICENSE](LICENSE).
