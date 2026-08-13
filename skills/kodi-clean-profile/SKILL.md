---
name: kodi-clean-profile
description: >
  Isolate a Kodi problem by reproducing it in a clean profile with no add-ons,
  then bisect to find the culprit. Use when Kodi is misbehaving on an install with
  third-party add-ons, when you need a known-good baseline to compare against, or
  when you want to test something without touching a user's real setup. Covers
  making the profile, the switching calls that lie about succeeding, and how to
  bisect without a dozen restarts.
license: CC-BY-SA-4.0
metadata:
  category: diagnosis
  verified-kodi: "21.3 Omega"
  verified-platform: "Linux x86_64"
  verified-date: "2026-08-13"
  verified-method: "observed"
---

# Isolating with a clean profile

Most "Kodi is broken" is one bad add-on. A clean profile settles that in minutes,
and it does so **without uninstalling anything the user cares about** — which
matters, because you are usually working on someone's real media setup and they
would like it back.

A Kodi profile has its own `userdata` tree: its own databases, its own settings,
and its own record of which add-ons are enabled. The add-ons themselves are
installed once system-wide; a profile only decides which ones are *on*.

## Make one

Settings > Profiles > Add profile. Give it a name, and when Kodi asks, choose to
start with **default settings and no media sources**. That is the whole point —
a profile cloned from the current one inherits the problem.

The new tree appears at:

```
~/.kodi/userdata/profiles/<name>/
```

## Switching is where this goes wrong

**`Profiles.LoadProfile` returns `"OK"` without switching.** The result is an
acknowledgement that the request was accepted, not that anything happened. If the
outgoing profile has an add-on whose service will not stop — which is exactly the
situation you are debugging — the switch silently never completes.

Always read back, and treat a timeout as wedged rather than slow:

```sh
kodi-remote get Profiles.LoadProfile '{"profile":"clean"}'
for i in $(seq 1 20); do
  kodi-remote get Profiles.GetCurrentProfile '{"properties":["label"]}' | grep -q clean && break
  sleep 1
done
```

**A modal dialog blocks the switch entirely.** A Yes/No dialog on the current
profile prevents `LoadProfile` from completing at all, and by the time you notice
the hang the switch has already failed. Check before switching:

```sh
kodi-remote get GUI.GetProperties '{"properties":["currentwindow"]}'
```

Once wedged, a restart is usually the only way out — see
[`kodi-process-control`](../kodi-process-control/SKILL.md), and mind the wrapper
trap there, because a half-killed Kodi makes this considerably worse.

## Enabling add-ons in the profile you actually meant

**`Addons.SetAddonEnabled` has no profile argument.** It acts on whichever profile
is currently loaded. Enable something while on the wrong profile and it silently
lands in the wrong place — which destroys the isolation you built the profile for,
with no error at all, and leaves you comparing two identical setups.

Verify against the profile's own database rather than trusting the call:

```sh
sqlite3 ~/.kodi/userdata/profiles/<name>/Database/Addons33.db \
  "SELECT addonID, enabled FROM installed WHERE enabled=1;"
```

The master profile's copy is at `~/.kodi/userdata/Database/Addons33.db`. The
schema number is Kodi-21-specific — check the real filename before assuming it.

## Bisecting without a dozen restarts

Switching profiles is slow and fragile. Editing a **non-active** profile's
database directly is neither:

```sh
sqlite3 ~/.kodi/userdata/profiles/<name>/Database/Addons33.db \
  "UPDATE installed SET enabled=0 WHERE addonID IN ('a','b','c');"
```

Kodi reads the file when it loads that profile, so the loop becomes: edit while
on another profile, switch in, test, switch out, edit again. Only ever touch a
profile Kodi does not currently have open.

Bisect in halves rather than one at a time. Twenty add-ons is five rounds, not
twenty.

## What this proves

| Result | Conclusion |
|---|---|
| Reproduces on a clean profile | Not an add-on. Look at Kodi itself, the skin, or the hardware. |
| Does not reproduce | An add-on. Bisect. |
| Reproduces only with add-ons *and* the user's skin | Try the clean profile with the user's skin — skins have their own failure modes. |

A clean profile also gives you a **baseline** for anything you want to measure,
which matters because Kodi's own resident set dominates absolute numbers. See
[`kodi-process-control`](../kodi-process-control/SKILL.md).

## What fails silently

- `LoadProfile` returns `"OK"` for a switch that never happened.
- A modal blocks switching with nothing surfaced to the caller.
- `SetAddonEnabled` succeeds against the wrong profile.
- A profile created *from* the current one inherits the problem, and looks clean.

## Open questions

- Whether Kodi caches any part of a non-active profile's add-on state in memory,
  which would make a direct database edit take effect late or not at all, has not
  been tested. Verify the enabled set after switching in, at least the first time.
- Whether a clean profile fully isolates *binary* add-ons — which are loaded
  differently from Python ones — has not been confirmed.

## See also

- [`kodi-profiles`](../kodi-profiles/SKILL.md) — the switching mechanics in full
- [`kodi-triage`](../kodi-triage/SKILL.md) — where this step sits in the ladder
- [`kodi-library-data`](../kodi-library-data/SKILL.md) — the databases involved
