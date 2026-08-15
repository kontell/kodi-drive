---
name: kodi-orientation
description: >
  Start here for any Kodi work. The map of what is in kodi-drive, the four working
  rules that prevent most wasted effort, and how Kodi differs from software you
  have worked on before. Use at the beginning of a Kodi task — writing an add-on
  or skin, debugging an install, or answering a Kodi question — especially if you
  have not worked on Kodi recently.
license: CC-BY-SA-4.0
metadata:
  category: orientation
  verified-kodi: "21.3 Omega, 22.0b1 Piers"
  verified-platform: "Linux x86_64, Android TV"
  verified-date: "2026-08-13"
  verified-method: "observed"
---

# Working on Kodi

## The one thing to understand first

**Kodi fails silently, by default, almost everywhere.**

A malformed skin include is logged and dropped, and the window renders without
it. A plugin route that forgets to close its handle hangs its caller with no
timeout. `<reuselanguageinvoker>` in the wrong element is never parsed, and
nothing is logged either way. `Profiles.LoadProfile` returns `"OK"` for a switch
that never happens. A settings file reports a value that was changed two days
ago.

None of these raise. Each looks like something else — a dropped keypress, a slow
network, an add-on that ignores you, your own misunderstanding.

**So: do not reason about what Kodi will do. Run it and look.** That is the
single highest-value habit here, and everything below follows from it.

## Four rules

**1. Get your hands on a real Kodi, and ask if you do not have one.**

Verify at planning time, not just at the end. Local, SSH, ADB, or JSON-RPC all
work — [`kodi-connect`](../kodi-connect/SKILL.md) finds one on the network before
you have to ask, then walks a user through granting access if needed.

If access is not available, say plainly what you can and cannot conclude without
it. Do not quietly degrade to guessing because asking felt like an imposition.
One question costs a minute; a confident wrong answer costs an afternoon and
sends the user down the wrong path.

**2. Verify by running, not by reading.**

"The XML looks right" is not a result. Reload the skin and look
([`kodi-screenshot-review`](../kodi-screenshot-review/SKILL.md)). Query state and
read it back ([`kodi-jsonrpc`](../kodi-jsonrpc/SKILL.md)). Kodi will disagree with
you more often than you expect.

**3. Read the source of whatever you are interfacing with.**

Kodi itself, the add-on you depend on, the server you are talking to. Recall of a
specific API at a specific version is not good enough, and Kodi's
version-to-version differences are exactly where the expensive bugs live.

Do not walk the disk looking for the tree. In this order:

1. **Look briefly.** `ls` a handful of conventional names next to the project —
   `ref/kodi-piers-full`, `ref/kodi-omega-full`, `kodi-omega`, `kodi-piers`.
   That is the whole search. A recursive `find` from `$HOME` or the working
   tree is not a brief look.
2. **If none of those exist, ask where the tree is.**
3. **If there is no tree, ask permission to clone.** A Kodi source checkout is
   large. Do not clone unbidden. The command, once you have it, is in
   [`kodi-source-map`](../kodi-source-map/SKILL.md).

**4. Credentials go in a file, never in a repo and never in your output.**

`~/.config/kodi-drive/targets.env`, mode 0600. **Never `cat` it** — session
transcripts record everything printed and are not scrubbed. And note that
**kodi.log itself carries credentials**: Kodi and `inputstream.adaptive` write
full stream URLs including `api_key=` at debug level, which no add-on can
prevent.

## The map

**Something is broken and you do not know why** →
[`kodi-triage`](../kodi-triage/SKILL.md). It routes everything else.

**Need to check what Kodi actually does** →
[`kodi-source-map`](../kodi-source-map/SKILL.md) to find it,
[`kodi-architecture`](../kodi-architecture/SKILL.md) for how the pieces run.

**Getting and using a Kodi**
[`kodi-connect`](../kodi-connect/SKILL.md) ·
[`kodi-jsonrpc`](../kodi-jsonrpc/SKILL.md) ·
[`kodi-ui-navigation`](../kodi-ui-navigation/SKILL.md) ·
[`kodi-screenshot-review`](../kodi-screenshot-review/SKILL.md) ·
[`kodi-adb`](../kodi-adb/SKILL.md) ·
[`kodi-test-rig`](../kodi-test-rig/SKILL.md)

**Finding out what happened**
[`kodi-logs`](../kodi-logs/SKILL.md) ·
[`kodi-freeze-diagnosis`](../kodi-freeze-diagnosis/SKILL.md) ·
[`kodi-known-defects`](../kodi-known-defects/SKILL.md) ·
[`kodi-clean-profile`](../kodi-clean-profile/SKILL.md) ·
[`kodi-process-control`](../kodi-process-control/SKILL.md) ·
[`kodi-profiles`](../kodi-profiles/SKILL.md)

**Playback and streams**
[`kodi-playback-resume`](../kodi-playback-resume/SKILL.md) ·
[`kodi-paplayer`](../kodi-paplayer/SKILL.md) ·
[`kodi-playback-tempo`](../kodi-playback-tempo/SKILL.md) ·
[`kodi-inputstream`](../kodi-inputstream/SKILL.md) ·
[`kodi-pvr-addon`](../kodi-pvr-addon/SKILL.md) ·
[`kodi-pvr-menu-hooks`](../kodi-pvr-menu-hooks/SKILL.md)

**Writing an add-on**
[`kodi-addon-manifest`](../kodi-addon-manifest/SKILL.md) ·
[`kodi-plugin-handles`](../kodi-plugin-handles/SKILL.md) ·
[`kodi-addon-lifecycle`](../kodi-addon-lifecycle/SKILL.md) ·
[`kodi-announcements`](../kodi-announcements/SKILL.md) ·
[`kodi-addon-driving`](../kodi-addon-driving/SKILL.md) ·
[`kodi-performance`](../kodi-performance/SKILL.md) ·
[`kodi-idle-screensaver`](../kodi-idle-screensaver/SKILL.md)

**Skinning**
[`kodi-skin-xml`](../kodi-skin-xml/SKILL.md) ·
[`kodi-skin-res-scaling`](../kodi-skin-res-scaling/SKILL.md) ·
[`kodi-keymaps`](../kodi-keymaps/SKILL.md)

**Kodi's own data**
[`kodi-library-data`](../kodi-library-data/SKILL.md) ·
[`kodi-library-nodes`](../kodi-library-nodes/SKILL.md) ·
[`kodi-database-writing`](../kodi-database-writing/SKILL.md) ·
[`kodi-texture-cache`](../kodi-texture-cache/SKILL.md)

**Binary add-ons**
[`kodi-binary-build`](../kodi-binary-build/SKILL.md) ·
[`kodi-android-ndk`](../kodi-android-ndk/SKILL.md) ·
[`kodi-binary-settings`](../kodi-binary-settings/SKILL.md)

**Shipping it**
[`kodi-versions-abi`](../kodi-versions-abi/SKILL.md) ·
[`kodi-addon-release`](../kodi-addon-release/SKILL.md) ·
[`kodi-contributing`](../kodi-contributing/SKILL.md)

**Adjacent systems**
[`jellyfin-client`](../../adjacent/jellyfin-client/SKILL.md)

**Working with this repo**
[`contribute`](../contribute/SKILL.md) ·
[`audit`](../audit/SKILL.md)

## Things that surprise people coming from other software

- **The hardware is slow.** Identical Python work measured ~170x slower on an ARM
  TV box than on a desktop. A 130 ms operation becomes 22 seconds. Design
  decisions that are obviously fine locally are not.
  ([`kodi-performance`](../kodi-performance/SKILL.md))
- **Most APIs you want exist twice, differently.** JSON-RPC and the Python API
  overlap without matching, and `JSONRPC.Introspect` will confirm a method the
  Python side does not have.
- **Versions diverge meaningfully.** Omega and Piers differ in database schema,
  image handling, ABI floors, and behaviour. "Kodi does X" is usually incomplete.
- **A user's install is not your install.** Many have dozens of third-party
  add-ons, and one misbehaving service can take down every other Python add-on on
  the box. Assume an add-on until proven otherwise.
- **The UI is not a source of truth.** It shows what was drawn, not what was
  written.

## Before you finish

If you learned something general — how Kodi behaves, what breaks, what a log line
means — **it belongs in this repo, not in the project's `CLAUDE.md` or your
memory.** That is how it gets rediscovered ten times instead of once.

**Run [`contribute`](../contribute/SKILL.md).** It walks the whole loop, and its
first step is deciding whether there is anything to contribute — which for most
sessions there is not.

The bar is verification, not certainty: if you ran it, contribute a skill; if you
only saw it, open an issue. Both are wanted. See
[CONTRIBUTING.md](../../CONTRIBUTING.md).

## See also

- [README](../../README.md) — the full index and installation
- [Kodi wiki](https://kodi.wiki) — the reference this repo deliberately does not
  duplicate
