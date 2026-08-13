# kodi-drive — a shared Kodi knowledge repo for coding agents

> Implementation plan. **Status as of 2026-08-13: phases 0–3 and 5 done, 13 skills,
> 6 helpers, all verified against a live Kodi 21.3. Phase 4 (the harvest), phase 6
> (deep dive), phase 7 (stripping the source repos) and the `<DEVBOX>` survey remain.**
>
> Private strings in this document use the placeholder convention defined below
> (`<JELLYFIN_HOST>`, `/home/<user>/`, …) because this file ships in the repo.

## Context

Hard-won Kodi knowledge is scattered, machine-local, and unshareable. A survey of
`/media/minipie/bluecon/dev/` and `ref/` found:

- **8 `CLAUDE.md` files** (32–270 lines) mixing project facts with generic Kodi knowledge.
- **One skill**, `~/.claude/skills/kodi-drive/SKILL.md` (414 lines + `screenshot-review.md`). Most of it is
  generic Kodi knowledge wearing add-on-specific clothes.
- **~100 memory notes** across 12 project dirs under `~/.claude/projects/*/memory/`, fragmented across dead
  path slugs — skin.contuary's are split across **four** slugs as the repo moved; pvr.kofin's six are
  stranded under an old slug while its current slug has 8.9 MB of transcripts and zero memories.
- **`dev/notes/`** — 19 markdown post-mortems, **the densest source in the estate**, plus
  `plugin.video.kofin/docs/` (23 files + 8 audits) and `script.music.restore/docs/INVESTIGATION.md`
  (560 lines). None of it is a git repo or reachable from any project's context.
- **Five helper scripts** — `~/bin/kodi-{remote,shot,diff,logtail,builtin}` — that the skill, ~150 of the
  215 global permission entries, and several memory notes all depend on. **They exist in no repo.**
- **Zero** project-scoped skills, agents, commands, hooks, or MCP config. Every `.claude/` directory in
  both trees contains exactly one file: `settings.local.json`, an accreted permission allowlist.

The material is much richer than a knowledge-consolidation exercise usually is. It includes **four
apparently-unreported upstream Kodi/ISA defects**, measured performance data on real low-power hardware,
and debugging techniques that took hours to discover. None of it travels with a clone, survives a
directory move, or helps anyone else.

**Decisions taken:** repo starts **private**, flips public at Phase 5 once scrubbing is proven. Deep dive
is scoped to **orientation + source map only** for now. Kontell pipeline and Jellyfin-client knowledge
**both go in, scrubbed**.

---

## Step 0 — security, before anything else

All eleven `kontell` repos are **already public**. This is containment, not prevention.

**Live credentials in agent-readable files:**

| Location | Exposure | Git status |
|---|---|---|
| `dev/pvr.kofin/CLAUDE.md:90` | Jellyfin hostname + **working api_key** + real UserId — and line 91 *tells the agent to use it* | gitignored |
| `dev/plugin.audio.koshelf/.claude/settings.local.json` | Audiobookshelf bearer JWT ×12 | local |
| `dev/pvr.kofin/.claude/settings.local.json` | Jellyfin api_key ×3 + transcode URLs with session ids | local |
| `ref/jellyfin/.claude/settings.local.json` | Jellyfin api_key ×6 + UserId + item GUIDs | local |
| `dev/plugin.video.kofin/CLAUDE.md:27` | JSON-RPC credentials | **public** |
| `dev/skin.contuary/CLAUDE.md:81` | `/home/<user>/...` | **public** |
| 7 memory notes | incl. `jellyfin-test-api.md` — server URL, LAN IP, api_key, UserId, **test-user password** | local |

**The worst item is not a credential file.** `dev/notes/kodi-jobmanager-deadlock-2026-08-08/` is an 11.6 MB
evidence bundle holding a full unfiltered `adb bugreport` (`br.zip`, 8.4 MB) and a 3.3 MB raw `kodi.log`
containing **302 occurrences of a live IPTV stream token**, signed YouTube CDN URLs embedding **the
household's public IP**, SMB hostnames and share paths, the device model and build id, and a full add-on
inventory. `notes/` is not a git repo, so none of it has been pushed — but it sits inside a tree that is
otherwise all git working copies, and it is one `git add` from being published.

**Scale of the scrubbing problem — corrected 2026-08-13.** An earlier count put the personal Jellyfin
hostname at ~2,300 occurrences. That figure is real but misleading: **2,296 of them are inside the raw
3.3 MB `kodi.log` in the evidence bundle**, which is never harvested. The markdown Phase 4 actually
touches holds **15** — 2 in `notes/*.md` and 13 across `plugin.video.kofin/docs/`.

So the redaction is a handful of substitutions, not a bulk job. The mapping-based redactor is still the
right tool — deterministic, repeatable, and it catches what an eye skips — but it is not the bottleneck
it looked like, and Phase 4 is correspondingly cheaper than planned.

Actions:
1. ~~Rotate the Jellyfin api_key~~ — **done**. Still outstanding: the Audiobookshelf JWT, and the
   test-user password in `jellyfin-test-api.md`.
2. **Audit `pvr.kofin` history** — commit `1265711` records that `CLAUDE.md` was gitignored *because* it
   held API keys. Confirm no earlier commit in that public repo contains them. The key is rotated, so this
   is now about whether a history rewrite is still warranted, not about active exposure.
3. Quarantine the deadlock evidence bundle outside the dev tree, and add a global gitignore for
   `*.log`, `br.zip`, `bugreport*`.
4. Move every value behind the credential convention below.
5. Repeat 1–4 on `<DEVBOX>` (see [Second machine](#second-machine) below) — its `.claude` state has never
   been surveyed and is likely to hold the same class of artefact.

---

## Prior art — checked; the niche is open

**[`xbmc/kodiai`](https://github.com/xbmc/kodiai)** is Team Kodi's own LLM integration: a hosted GitHub App
doing PR auto-review, `@kodiai` assistance, and issue triage on the xbmc repos. Created 2026-02-08, still
shipping (v0.60, 51+ milestones, last push 2026-08-11). Relevant:

- It runs a **6-corpus hybrid retrieval** system (code, review comments, **the Kodi wiki**, code snippets,
  issues, canonical current-code).
- It **already reviews add-on repository PRs against the Kodi add-on submission rules**, loaded from
  `https://kodi.wiki/view/Add-on_rules`.
- Its **"Epistemic Guardrails"** are a 3-tier claim classifier (`diff-grounded` / `inferential` /
  `external-knowledge`) that silently deletes ungrounded claims. Stated principle: *"Silent omission is
  preferred over visible hedging … because hedged claims still influence the reader and create noise."*
  That is a solved version of the verified-findings problem below; we adopt its shape.
- Its `.gsd/` and `docs/superpowers/` trees show the maintainers already use Claude Code skills.

**`xbmc/kodiai` is licensed "Proprietary. All rights reserved."** Align with the design; copy no text.

Everything else: ~6 tiny `kodi-mcp-server` repos (0–5 stars) doing consumer "play my movie" control.
No `awesome-kodi-development`, no Kodi `SKILL.md` anywhere, and `xbmc/xbmc` has no `AGENTS.md`,
`CLAUDE.md`, or copilot instructions.

**Scoping rule that follows:** the wiki and the source are already covered by kodiai's corpora. kodi-drive's
niche is **what is in neither** — procedure, tooling, live-testing loops, symptom→cause maps, and gotchas.
Every skill must pass *"could a bot have got this from the wiki or by grepping the source?"* If yes, link.

---

## Design

### Format: Agent Skills, packaged as a Claude Code plugin

`SKILL.md` is the [Agent Skills open standard](https://agentskills.io), so the repo is not Anthropic-locked.
Plugin packaging buys three things that serve "minimum context cost" directly:

1. **Progressive disclosure** — only each skill's name + description sits in context (1,536-char cap each).
   ~35 skills ≈ 7 KB standing cost for a full Kodi expert on tap.
2. **`bin/` on PATH** — a plugin's `bin/` is added to PATH and invokable as a bare command. **This is where
   the five `~/bin/kodi-*` scripts go.** A bot runs `kodi-remote ok` instead of reading 40 lines on
   constructing a JSON-RPC call. Biggest single context saving available.
3. **Namespacing** — plugin skills resolve as `kodi-drive:<skill>`, so no collisions.

| Audience | Mechanism |
|---|---|
| Maintainer, now | Clone to `~/.claude/skills/kodi-drive/`. A `.claude-plugin/plugin.json` under a skills dir auto-loads as `kodi-drive@skills-dir` — **no marketplace, no install**. `SKILL.md` edits take effect immediately; `/reload-plugins` for `bin/` and hooks. |
| Other Claude Code users | `/plugin marketplace add kontell/kodi-drive` → `/plugin install kodi-drive` (needs `.claude-plugin/marketplace.json`) |
| Non-Claude agents | `git clone` + read `README.md` — the vendor-neutral index |

### Repo layout

```
kodi-drive/
├── README.md                   # index + user guidance + house rules
├── CONTRIBUTING.md             # verification bar, privacy, dedup, add-on policy
├── LICENSE                     # CC BY-SA 4.0 prose; GPL-2.0-or-later for bin/ + scripts/
├── .claude-plugin/{plugin,marketplace}.json
├── skills/<name>/SKILL.md      # generic Kodi knowledge
├── addons/<addon-id>/SKILL.md  # per-add-on
├── adjacent/jellyfin-client/   # Kodi-adjacent server knowledge
├── bin/                        # kodi-remote, kodi-shot, kodi-diff, kodi-logtail, kodi-builtin
├── scripts/{validate.py,scrub.py,new-skill.sh}
├── templates/
└── .github/{PULL_REQUEST_TEMPLATE.md,ISSUE_TEMPLATE/,workflows/validate.yml}
```

CC BY-SA 4.0 keeps the prose compatible with quoting the (CC BY-SA) Kodi wiki; GPL-2.0-or-later on the
scripts sits comfortably in the Kodi ecosystem.

### The verification bar

Prose pleas don't make bots restrict themselves to verified findings; **structure plus mechanical gates**
does. Four layers:

**1. Every claim carries a tier** (adapted from kodiai's model):

| Tier | Means | Evidence required |
|---|---|---|
| `observed` | Ran against a live Kodi, saw the result | The command and its actual output |
| `sourced` | Traceable to Kodi/add-on source or official docs | `file.cpp:1234` or a docs URL |
| `inferred` | Deduction from the above, **labelled as such** | The premises |

Anything else is not a skill. It is an issue.

**2. Schema, not adjectives.** Bots follow schemas far more reliably than exhortations. Enforced by
`validate.py` in CI:

```yaml
---
name: kodi-logs
description: <what + when to use>
license: CC-BY-SA-4.0
metadata:
  verified:
    kodi: ["21.3 Omega", "22.0b1 Piers"]
    platform: ["Linux x86_64", "Android TV"]
    date: "2026-08-13"
    method: observed        # observed | sourced | inferred
---
```

**3. A hedge lint.** CI fails on `probably|should work|I think|might be|seems to|presumably|in theory|
likely|may need to|try …`, printing the offending line — a soft norm becomes a red X. **It has an escape
hatch:** content under `## Open questions` is exempt. Without a legal home for uncertainty, bots launder it
into confident prose, which is worse.

**4. Give low confidence a destination.** The PR template opens with a hard gate:

> **STOP.** If you did not run this against a live Kodi, or cannot cite a source file or official doc —
> **do not open this PR.** Open an *Unverified observation* issue instead. An issue is welcome and useful.
> A wrong skill is worse than no skill, because every future agent trusts it.

Then per-claim blocks the author must *fill*, not tick — Kodi version, platform, command run, actual output
in a fenced block. An empty fence is visible to a reviewer and to CI in a way an unticked box never is.

### Privacy and security

Machine-local private facts stay in `~/.claude/projects/<slug>/memory/` — outside every repo.

**Credential convention:** `~/.config/kodi-drive/targets.env`, mode 0600, never in a repo, holding named
targets (`KODI_<name>_TRANSPORT` = local|ssh|adb, `_RPC`, `_ADDR`, `_USER`, `_PASS`). The `bin/kodi-*`
scripts read it; skills only ever refer to `$KODI_TARGET`. **Skills must instruct bots never to `cat` it** —
session transcripts capture everything printed, and this box already holds 728 MB of them.

**`scripts/scrub.py`** — pre-commit hook *and* CI. Two modes:
- *Detect*: IPv4/IPv6 (allowing loopback and RFC 5737 doc ranges), MACs, `.local`/`.xyz` hostnames,
  ADB `host:port`, emails, `/home/<user>/`, `smb://`/`nfs://`, `Bearer `, JWTs, `api_key=`, `token=`,
  `password=`, `X-Emby-Token`, `X-MediaBrowser-Token`, long base64 blobs.
- *Redact*: a deterministic mapping file (gitignored) turning known private strings into stable
  placeholders — `<JELLYFIN_HOST>`, `<KODI_HOST>`, `<ADB_SERIAL>`, `<USER>`. **This is what makes the
  ~2,300-occurrence `notes/` migration tractable**, and stable placeholders keep the prose readable.

Plus `gitleaks` in CI as an independent second pass.

### Add-on policy

Follow Kodi's own rules by reference, never restated:
[Add-on rules](https://kodi.wiki/view/Add-on_rules) ·
[Forum rules / Banned add-ons](https://kodi.wiki/view/Official:Forum_rules/Banned_add-ons) ·
[Submitting Add-ons](https://kodi.wiki/view/Submitting_Add-ons).

Out: add-ons whose purpose is accessing infringing content; "builds", wizards, and the forks on Kodi's
banned list; DRM circumvention. **Explicitly in** (worth stating, since it is the common misconception):
scraping a public website to build an unofficial add-on is not piracy and is welcome. Such add-ons are
largely not on GitHub anyway — a keyword denylist would false-positive more than it catches, so handle it
with a CONTRIBUTING section, a PR checkbox, and CODEOWNERS review.

---

## Skill catalogue

★ = evidence already in hand, ☆ = new.

**Entry points** — ★`kodi-orientation` (the map + house rules; the one worth auto-loading) ·
☆`kodi-triage` (the *"Kodi no work good"* router)

**Access & control** — split out of the existing 414-line skill: ☆`kodi-connect` ·
★`kodi-jsonrpc` · ★`kodi-builtins` · ★`kodi-adb` · ★`kodi-ui-navigation` · ★`kodi-screenshot-review`

**Observability**
- ★`kodi-logs` — debug logging **without the on-screen overlay**; never read the file whole; and a
  **signature table**: `Window Init (<path>)` proves which XML loaded, `waiting on thread <id>`,
  `LoadDetails: Unsupported item type`, `Thread JobWorker terminating (autodelete)` ×4 with one worker
  unaccounted for and no `JobWorker start` after (an hour of warning before a freeze).
- ★`kodi-crash-triage` — **native backtraces on a retail Android TV without root** via
  `adb bugreport br.zip` → `------ VM TRACES JUST NOW ------` (`dumpstate` runs privileged and SIGQUITs
  every process; direct `kill -3` fails and `/data/anr/*` is `0600 system`). logcat's ring buffer is
  minutes deep under DPAD spam, so pull it immediately.
- ★`kodi-perf-diagnosis` — **`voluntary_ctxt_switches` at ~193/s across every Python thread is GIL
  starvation**, not idle polling (1/0.005 is CPython's default switch interval); sample CPU over minutes
  not seconds (a 61 s window read 91% against a 13-minute average of 24%); a Python-wide freeze separates
  from a single-add-on bug by counting Python log lines either side of the moment (933 → 0).

**Python add-on development**
- ★`kodi-python-runtime` — runtime-only `xbmc*` modules; `special://` + `translatePath`; the **string
  cache** (a new `30xxx` id renders blank until a *full restart*); `import requests` costs **1.11 s** inside
  Kodi's Python and `.pyc` doesn't help, while `http.client`/`ssl`/`json` cost 0.000 s.
- ★`kodi-addon-manifest` — `<reuselanguageinvoker>` works **only** under `xbmc.addon.metadata`, is silently
  ignored under `pluginsource`, and nothing is logged either way (0.62–0.91 s → 0.17–0.25 s when right);
  **LibPath comes from the first `<extension>`**, which is what `RunScript` resolves; Kodi **does not
  install optional dependencies**; `<visible>` needs `[square brackets]` (parentheses are infolabel syntax
  and fail the whole expression); `<visible>` cannot read a setting; `start="login"` fires on profile
  switch, **not** startup.
- ★`kodi-plugin-handles` — **every directory route must close its handle or it hangs its caller with no
  timeout**: `CScriptRunner::WaitOnScriptResult`'s first loop has no timeout at all. Before invoker reuse
  the interpreter died each time and it failed fast — which is what old fire-and-exit routes were written
  against. A node `<path>` carries a trailing slash; a dialog cannot open inside `GetDirectory`.
- ★`kodi-addon-lifecycle` — `xbmcaddon.Addon()` raises mid-update and **a setting write in that window is
  silently dropped**; "script didn't stop in 5 seconds" is **not a kill**; a stop flag in a *window
  property* is useless for orphan threads (measured: property-based abort 124 s vs generation-owned
  `threading.Event` **29 s** — identical-looking fixes, one does nothing); `abortRequested` means *Kodi is
  shutting down*, not *this add-on is bouncing*; two service generations overlap ~10 s.
- ★`kodi-threading` — callbacks arrive on **the announcement thread every add-on shares**, so HTTP there
  stalls every add-on on the box; connections must be thread-local; retries must be **per-method** (a
  replayed POST double-applies); bound writer queues (~490 MB measured) and never use a bare blocking
  `put`; `ThreadPoolExecutor.shutdown(wait=True)` deadlocks on an abandoned generator.

**Binary add-on development**
- ★`kodi-binary-build` — **the ABI floor is set by the build host, not the code**: a trivial `.so` built on
  glibc 2.42 still needs `__isoc23_strtoul@2.38`; build on `ubuntu:22.04` and it's gone. Pin a *container*,
  not a runner label. The superbuild forwards `CMAKE_*_FLAGS` but **not** linker flags — `LDFLAGS` is the
  injection point. `@ADDON_DEPENDS@` comes from the checked-out Kodi headers, so an unpinned ref moves your
  declared version with no commit of your own.
- ★`kodi-android-ndk` — four traps in sequence: NDK r19+ puts the triple in `CMAKE_C_COMPILER_TARGET` which
  ffmpeg's configure never reads; autoconf deps need `--host` or they try to *run* test binaries; `CPU` must
  be a CACHE var; gnutls autodetects the host libzstd. Plus NDK version roulette (r28c → r27c → r25c).
- ★`kodi-binary-safety` — jsoncpp's `asInt()` throws and **an escaped exception crosses the Kodi C ABI**;
  assigning to a joinable `std::thread` calls `std::terminate()`; never hold the model mutex across an HTTP
  GET; return cross-thread settings strings **by value**.
- ★`kodi-binary-settings` — the ABI delivers **only value-change callbacks**: no action-press callback, no
  builtin to write a setting, no way to close or observe your own settings dialog. *(Resolve first:
  `pvr.kofin/CLAUDE.md` calls its own format both "categorized" (:35) and "old flat" (:57, :98).)*
- ★`kodi-pvr-addon` — which UI path calls which entry point (window 10701 does **not** call
  `GetRecordingStreamProperties`); `CloseLiveStream()` doesn't fire on normal stop in v21; no player-event
  callbacks under inputstream-delegated playback.
- ★`kodi-vfs-http` — POST data Base64 via `postdata`; **unreachable server and expired token are
  indistinguishable** through Kodi's VFS, so never auto-clear credentials on a validation failure.

**Playback, streams, subtitles**
- ★`kodi-player-selection` — `<provides>` controls the browse category, not the player core.
- ★`kodi-resume-and-seek` — `StartOffset` vs `audiobook_bookmark`; **`PlayMedia`'s `resume` flag cannot
  resume a `plugin://` path** and silently downgrades; `Player.Open`'s `options.resume` is **silently
  ignored for a playlist**; handing Kodi a bare `plugin://` while something plays aborts the new demuxer
  because the outgoing stop reaches the app thread **103–105 ms after** `OpenFile` — every time.
- ★`kodi-subtitles` — sidecars are registered in `OpenInputStream`, *before* `OpenDemuxStream` adds the
  container's tracks, so they **lead** and every embedded ordinal shifts. Silent: the viewer just gets a
  neighbouring language. Kodi reads language and name **out of the filename**, with a measured grammar.
- ★`kodi-inputstream` — HLS `EXT-X-PLAYLIST-TYPE:EVENT` without `ENDLIST` reads as live; ActiveAE schedules
  against packet pts at *output* rate while the OSD wants *content* rate; FFmpeg 6 vs 7 differences.

**Skin engine**
- ★`kodi-skin-xml` — `ReloadSkin()` re-reads `xml/` but **not** `addon.xml`; a malformed include fails
  *silently*; Kodi's pugixml ends a comment at the first `-->` so a spec-exact validator rejects files Kodi
  loads fine; grouplist auto-wiring works only through direct focusable children; skin variables are
  **first-match-wins**.
- ★`kodi-skin-res-scaling` — an add-on's `resources/skins/default/1080i/` is auto-scaled into the skin's
  coord space while the skin's own `xml/` is taken as already-in-space; a skin file with the same basename
  wins → **don't fork script-addon WindowXMLs**; `<res>` needs a full restart.
- ★`kodi-skin-limits` — `Container(...)` resolves against **whatever window is active**, so a dialog hides a
  list from a script; `Control.IsVisible` reports the control's own condition, not its parent group's;
  builtins do not wait for each other; `<itemlayout>` can't resize at runtime and **nothing in Kodi
  measures rendered text**; add-ons cannot ship a keymap; a Kodi notification fits **~33 characters** and
  scrolls the rest (a truncation caught mid-scroll said the opposite of what it meant);
  `CGUIDialogSelect` makes pop-up and context menu **mutually exclusive**.
- ★`kodi-skin-testing` — the reload loop; `ReloadSkin()` reads the **installed** tree, not the dev tree.

**Kodi's own data**
- ★`kodi-database` — **never write the library through JSON-RPC** (announcer echo loop); direct SQLite
  raises no event, so widgets never move — and the trick is to scan **a directory that does not exist**,
  which completes in 0 s having probed nothing while still invalidating containers; **music has no
  `noUpdate` column**, so a bare `UpdateLibrary(music)` walks ~21k remote probes and overlapping scans have
  SIGBUS'd Kodi on Android; Kodi reserves `idArtist 1` for `[Missing Tag]`; nest two-DB writes so Kodi
  commits first; pull a DB **with its `-wal` and `-shm`**; Kodi 22's MyVideos 146→147 bump is **data-only**.
- ★`kodi-texture-cache` — the cache re-encodes to JPEG **only** when the source has no alpha, so any RGBA
  source costs the same twice (measured 3.6 MB → 698 KB by asking for WebP); lossless WebP is ARGB so it
  lands back on the PNG path; the decoder comes from the *extension* and Omega refuses where Piers sniffs;
  the cache **can be seeded** (special-type images are never re-validated) — CRC-32/MPEG-2 over the
  lowercased key, `sizes(size=1)` row mandatory, and the key differs between Omega and Piers.
- ★`kodi-library-nodes` — a bare-number `<label>` resolves against **Kodi's own** strings where the 30000+
  range is empty, so it renders untitled and fails silently; `CLibraryDirectory` hardcodes `isFolder=true`
  so a library node **can never** produce a pop-up; `GetNode` reads the profile's folder *instead of*
  Kodi's defaults, never merged.
- ★`kodi-widget-refresh` — `CDirectoryProvider` invalidates only for providers whose last fetch **included**
  the matching media kind, so **a widget that returned zero items is deaf to every announcement**; Kodi
  invalidates natively on `Player.OnPlay/OnStop` for `SortByNone`, which most skin widgets are; fingerprint
  what the UI renders, sum per-item hashes, fold in the count, and never hash a raw `lastplayed`.

**Packaging & release**
- ★`kodi-addon-release` — **a release published by a workflow using the default `GITHUB_TOKEN` raises no
  release event** (the single most duplicated fact in the corpus — five separate files);
  `actions/upload-artifact` defaults to `if-no-files-found: warn`, and one add-on shipped **10 assets from
  12 green jobs** with a platform silently missing from the served repo for a whole release;
  `actions/checkout` checks out **the tag's** tree, so a version grepped from it can disagree with the tag
  (a release tagged `v0.9.1`, titled 0.9.0, containing 0.9.0 zips); package by exclude-list not
  include-list; `paths-ignore` on `pull_request` reports **no checks at all**.
- ★`kodi-versions-abi` — Kodi accepts an add-on only within `[MIN, current]`; Omega PVR 8.3.0/MIN 8.2.0 has
  a cushion, Kodi 22's 9.2.0/MIN 9.2.0 has **none**, so the day master bumps, supporting Beta 1 and
  supporting master tip become mutually exclusive.
- ★`kodi-addon-identity` — a renamed id is a **different add-on** to Kodi and the old install must be
  removed by hand; disjoint channel branches make `git log a..b` meaningless.

**Cross-cutting** — ★`kodi-addon-ipc` · ★`kodi-idle-screensaver` (`ActivateScreenSaver` is **inhibited
during VideoPlayer playback**) · ★`kodi-secrets-hygiene` (**Kodi core and inputstream.adaptive log full URLs
at debug level**, which the add-on cannot prevent — so user debug logs are credential-bearing, exactly as
this estate's own evidence bundle demonstrates)

**Kodi core defects — upstream-worthy, and the seed of `kodi-triage-map`**
- ☆`kodi-known-defects` — **`CJobManager` permanently stops dispatching if any callback blocks**
  (Kodi 22 regression since `10e6892920`: `OnJobComplete()` erases from `m_processing` before invoking
  callbacks, so a blocked worker counts as idle; the rest age out and `StartWorkers()` forever takes the
  "a sleeping worker will take it" branch — **no job anywhere in Kodi ever runs again**, no log line, no
  recovery) — **filed upstream, with a PR open**; link both from the skill so the entry ages into
  "fixed in <version>" rather than going stale. Plus three not yet filed:
  `CDVDAudioCodecFFmpeg::GetData`'s unbounded channel count against a fixed `data[16]`;
  `inputstream.adaptive` having **no MP3/MP2 codec identity** and mislabelling `mp4a.40.34` as AAC; ISA
  clamping live seeks with no retry. Each needs a `status:` field (`filed` / `pr-open` / `merged` /
  `unreported`) so the skill stays honest about what a reader will actually hit.

**User-facing debugging** — ☆`kodi-clean-profile` · ☆`kodi-test-rig` (Android phone as a test device,
including setting Kodi's screensaver so the **device** screensaver and display-off never fire)

**Per-add-on** (`addons/`) — the eight projects, plus `addons/kontell-pipeline` for the shared-but-not-
universal release machinery (`tools/build.py` is literally the same file across add-ons). Generalisable
lessons go to `kodi-addon-release`; Kontell specifics stay here.

**Adjacent** (`adjacent/jellyfin-client/`) — Etags cover metadata **not userdata** (proven twice); userdata
is keyed by **provider id** so a re-added item silently inherits the previous incarnation's row, with no
event of any kind; `UserDataChanged` is fanned out to every session *containing* the user, so "Add user"
subscribes you to a co-watcher's entire stream (present in stock `jellyfin-kodi` since Sept 2018); a
`DirectPlayProfile` and a `TranscodingProfile` answer different questions; the HLS master advertises the
codecs it *assumed*, not what the segments carry.

### `kodi-triage` — making a dumb prompt work

The design point is that the bot must **ask for what it needs rather than making do**. Mandatory gate
before any theorising:

1. **Find the Kodi before asking for it.** `kodi-connect` leads with **LAN auto-discovery**, so the agent
   arrives at the user with "I found a Kodi 21.3 at <addr> — is that the one?" rather than an open
   question. Order: mDNS/Zeroconf (`_xbmc-jsonrpc._tcp`, `_xbmc-jsonrpc-h._tcp`, `_xbmc-events._udp` via
   `avahi-browse`/`dns-sd`) → SSDP M-SEARCH if the UPnP renderer is on → `adb devices` plus
   `_adb-tls-connect._tcp` for Android 11+ wireless debugging → port-scan fallback on 8080/9777. Confirm
   every hit with `JSONRPC.Ping`, then `Application.GetProperties` for version and name.
2. **Get access.** Only now offer the ladder — local / SSH / ADB / JSON-RPC over HTTP / "paste a log".
   Carry copy-paste, no-keyboard-required instructions per platform, including enabling debug logging on
   Android TV and via `advancedsettings.xml` with the overlay suppressed. **Turn debug logging on *before*
   the reproduction** — with it off you lose the `CServiceAddonManager: stopping <addon>` lines that name
   the culprit.
3. **Get a log.** Never read it whole; `kodi-logtail` + targeted greps.
4. **Establish the baseline.** If third-party add-ons are installed, create a clean profile and reproduce
   there first. Most "Kodi is broken" is one bad add-on — and this estate has the receipt: one add-on's
   service held the CPython GIL and **took down every other Python add-on on the box**, with C++ entirely
   unaffected and Kodi unable to shut down.
5. **Bisect**, then fix.

State plainly: *if you do not have access, ask for it — do not degrade to guessing.*

### The deep dive (scoped down)

Both trees are local: `ref/kodi-omega-full` (21.3) and `ref/kodi-piers-full` (22.0b1-Piers). Scope for now
is **one focused session** producing `kodi-architecture` (process model, `CApplication`, GUI/windowing,
`VideoPlayer`, add-on framework, DB layer, PVR, InputStream, skin engine) and `kodi-source-map` (how to find
things fast — naming conventions, where to grep first). Per-subsystem skills get added when real work
demands them, so they stay grounded. The `gh` issue-mining pass for a full `kodi-triage-map` is deferred;
`kodi-known-defects` seeds it in the meantime.

---

## Maintenance

**The core rule, in README, CONTRIBUTING, and `kodi-orientation`:**

> Broadly-useful Kodi knowledge does not go in a project's `CLAUDE.md` or memory. It goes to kodi-drive.
> Project files hold only: what this project is, its build/test/deploy commands, its local paths.

**Per-session loop** — a `/kodi-drive:contribute` skill: collect what was learned → grep existing skills for
overlap and **edit in place** rather than adding a near-duplicate → run `scrub.py` and `validate.py` →
branch, commit, open a PR with the template filled from real evidence.

**Dedup** — `/kodi-drive:audit` for periodic sweeps, plus a CI job that greps a PR's added claims against
existing skills and comments with near-matches. CONTRIBUTING carries an explicit prompt: *"Before adding a
skill, list the three existing skills closest to it and state why this is not an edit to one of them."*

**Staleness** — `validate.py` warns when `metadata.verified.date` is older than ~12 months or the Kodi
version list omits the current stable release.

---

## Migration

Staged, so nothing is deleted before its replacement is proven. Per source:

1. **Extract** → a kodi-drive PR (generic → `skills/`, add-on-specific → `addons/`).
2. **Verify** against a live Kodi.
3. **Only then** strip the source repo in a separate commit, leaving:

```markdown
## Kodi knowledge lives in kodi-drive
Shared Kodi knowledge is NOT in this file. Use the `kodi-drive:*` skills, or read
<kodi-drive>/README.md. Do NOT add generally-useful Kodi findings here — contribute
them to kodi-drive via `/kodi-drive:contribute`.
This file holds only: what this project is, its build/test/deploy commands, its local paths.
```

Sources in priority order: `dev/notes/` (densest) → `plugin.video.kofin/docs/` →
`script.music.restore/docs/INVESTIGATION.md` → the 8 `CLAUDE.md` files → the ~100 memory notes → git
histories. **Everything from `notes/` and `docs/` must go through `scrub.py --redact` first.**

**On "all skills in kodi-drive, only private memories local — any disadvantage?"** One real one: an add-on
skill lives in a different repo from its code, so it can drift, and a change touching both needs two PRs.
Mitigations: `metadata.verified` pins the version it was verified against, and `validate.py` flags drift.
The upside — one place to look, one to contribute, no fragmentation on directory moves — clearly wins. Note
the memory dirs have their own weakness: keyed by absolute path and already fragmented across four dead
slugs, so the plan also consolidates each add-on's memories into its current slug and points them at
`targets.env` rather than duplicating values.

---

## Second machine

Much of `pvr.kofin` and some other add-on work was done on a second box (`<DEVBOX>`). **The dev tree here is
an NFS mount of that machine**, so the *repo* content is already shared — but everything machine-local to it
is invisible from this side and has never been surveyed:

- `~/.claude/projects/*/memory/` — its own memory notes, under **its own path slugs**. If the tree is
  mounted at a different path there, the slugs differ, which adds a fifth axis to the fragmentation already
  found (skin.contuary's notes are split across four dead slugs on this box alone).
- `~/.claude/skills/` — possibly a divergent copy of the 414-line `kodi-drive` skill.
- `~/.claude/settings.json` — a second permission allowlist encoding a second workflow.
- `~/bin/kodi-*` — possibly divergent copies of the five helper scripts. **These must be reconciled before
  vendoring**, or `bin/` ships whichever version happened to be on the machine that ran Phase 2.
- `~/.claude/projects/*/*.jsonl` — transcripts, for the same reason they matter here.
- Any `notes/`-equivalent, build trees, or local-only docs.

Note that `<DEVBOX>` is also the Jellyfin test server, so its `.claude` state is likely to hold the same
class of credential artefact found on this box. Treat Step 0 as applying there too.

### Access — no new sharing needed

Do **not** export the home directory. NFS auth is host/UID-based, and `~/.claude/.credentials.json` holds a
live OAuth token; putting that on the wire for a one-off harvest is a bad trade.

Instead: **run a Claude Code session on `<DEVBOX>` directly.** The kodi-drive repo is already visible from
both machines over the existing NFS mount, so that session can write its harvest straight into the shared
tree — `docs/harvest-devbox.md` — and this machine picks it up with no extra plumbing at all. That is the
whole handoff.

Give it the same brief used for this survey: inventory `~/.claude/` (skills, memory dirs, settings,
transcripts, plans), diff `~/bin/kodi-*` against this box's copies, list every `CLAUDE.md` and `.claude/`
under its local trees, and flag credentials and private identifiers by **location only, never by value**.
Run `scrub.py --detect` before anything crosses into the repo.

If a session there is inconvenient, SSH plus a read-only survey script gets most of it — but it will miss
the transcripts, which are large and where several of the best findings on this box came from.

---

## Build order

| Phase | Deliverable |
|---|---|
| **0** | ✅ Global gitignore hardened; pvr.kofin history audited (key was public in f2d1e98 since 2026-03-29, now rotated). Outstanding: Audiobookshelf JWT, test-user password. |
| **1** | ✅ Repo skeleton, validate.py, scrub.py, CI, templates, plugin manifests. |
| **1b** | ⬜ **Survey `<DEVBOX>`** — a session on that machine writes `docs/harvest-devbox.md` into the shared tree. |
| **2** | ✅ Five helpers vendored + kodi-discover added, all live-verified. Reconciliation against `<DEVBOX>` copies still pending. |
| **3** | ✅ Split into kodi-connect, kodi-jsonrpc, kodi-builtins (folded into kodi-remote), kodi-adb, kodi-ui-navigation, kodi-screenshot-review, kodi-addon-driving. |
| **4** | ⬜ Harvest `notes/` → `docs/` → CLAUDE.md → memories → git histories, redacting as you go. |
| **5** | ✅ kodi-triage, kodi-logs, kodi-clean-profile, kodi-test-rig, kodi-process-control, kodi-profiles, kodi-library-data. Repo still **private** — flip after phase 4 scrubbing. |
| **6** | ⬜ kodi-architecture + kodi-source-map (one session). |
| **7** | ⬜ Strip the source repos; install the pointer stanza; consolidate memories from both machines. |
| **8** | ⬜ /kodi-drive:contribute + /kodi-drive:audit; announce. File the three remaining upstream defects. |

## Verification

- `claude plugin validate ./kodi-drive` passes; `/plugin` lists `kodi-drive@skills-dir`; every skill is
  invocable as `/kodi-drive:<name>`.
- `bin/` scripts resolve as bare commands in a Bash call from a fresh session.
- **The end-to-end test that matters:** a fresh session in a bare directory, given only *"Kodi no work good,
  need help"*, loads `kodi-triage`, asks for device access, gets a log, and proposes a clean-profile bisect
  — with no project context at all.
- `scrub.py` over the whole tree returns clean; `gitleaks` clean; CI red on a deliberately-bad test PR
  (hedge word, missing frontmatter, planted fake IP → three distinct failures).
- **Gate on the public flip:** `scrub.py --detect` returns zero findings across every file, and a manual
  read of the ten largest migrated skills confirms no residual hostname, IP, or library-content fingerprint.
- Each migrated skill re-verified against live Kodi before its source repo is stripped.
