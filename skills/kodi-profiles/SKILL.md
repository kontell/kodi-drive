---
name: kodi-profiles
description: >
  Switch Kodi profiles from a script, and enable add-ons in the profile you
  actually meant. Use when isolating a problem in a clean profile, running A/B
  comparisons between add-on sets, or when Profiles.LoadProfile returns OK but
  nothing changes. Covers the silent failures in LoadProfile, the modal that
  blocks switching outright, and why Addons.SetAddonEnabled can install into the
  wrong profile without any error.
license: CC-BY-SA-4.0
metadata:
  category: diagnosis
  verified-kodi: "21.3 Omega"
  verified-platform: "Linux x86_64"
  verified-date: "2026-08-13"
  verified-method: "observed"
---

# Driving Kodi profiles

A separate profile is the best tool for isolating a problem — most "Kodi is
broken" reports are one bad add-on, and a clean profile proves it in minutes. But
the JSON-RPC surface for profiles reports success far more readily than it
delivers it.

## `Profiles.LoadProfile` returns `"OK"` without switching

The call returns `"OK"` immediately. That is an acknowledgement that the request
was accepted, **not** that the profile changed.

If the outgoing profile has an add-on whose service will not stop, the switch
never completes, and the RPC result gives no hint whatsoever. Kodi is now wedged
between profiles.

**Always confirm, and treat a timeout as wedged rather than slow:**

```sh
kodi-remote get Profiles.LoadProfile '{"profile":"test"}'

for i in $(seq 1 20); do
  current=$(kodi-remote get Profiles.GetCurrentProfile '{"properties":["label"]}')
  case "$current" in *'"test"'*) echo "switched"; break ;; esac
  sleep 1
done
```

Once wedged, restarting Kodi is usually the only fix — see
[`kodi-process-control`](../kodi-process-control/SKILL.md), and note the wrapper
trap there, because a half-killed Kodi makes this much worse.

## A modal dialog blocks switching entirely

A Yes/No dialog (window `10100`) open on the current profile prevents
`LoadProfile` from completing at all.

This matters for ordering: **any automation that switches profiles must already
have its dialog-answering thread running before it issues the switch**, not
started afterwards in response to a hang. By the time you notice the hang, the
switch has already failed and the dialog is holding it.

Check for one before switching:

```sh
kodi-remote get GUI.GetProperties '{"properties":["currentwindow"]}'
```

## `Addons.SetAddonEnabled` applies to the loaded profile

There is no profile argument. The call acts on whichever profile is currently
loaded — so enabling an add-on while on the wrong profile silently enables it
somewhere it does not belong.

In an A/B comparison this destroys arm isolation with no visible error: both arms
end up with the same add-on set and the results look merely uninteresting rather
than wrong.

**Verify against the target profile's own database rather than trusting the call:**

```sh
sqlite3 "$HOME/.kodi/userdata/profiles/<profile>/Database/Addons33.db" \
  "SELECT addonID, enabled FROM installed WHERE addonID='plugin.video.example';"
```

The master profile's database is at `~/.kodi/userdata/Database/Addons33.db`;
per-profile ones live under `userdata/profiles/<name>/Database/`.

## Editing a non-active profile's add-on state directly

A profile that is not loaded can have its add-on enablement changed by writing to
its `Addons33.db`:

```sh
sqlite3 "$HOME/.kodi/userdata/profiles/<profile>/Database/Addons33.db" \
  "UPDATE installed SET enabled=1 WHERE addonID='plugin.video.example';"
```

This is the way out when profile switching is itself the broken thing. Kodi reads
the file when it loads that profile.

Only touch a profile Kodi does not currently have open, and copy the `-wal` and
`-shm` files alongside the `.db` if you are snapshotting rather than editing —
reading the `.db` alone gives a stale view.

## What fails silently

- `LoadProfile` returns `"OK"` for a switch that never happens.
- A modal blocks the switch with no error surfaced to the caller.
- `SetAddonEnabled` succeeds against the wrong profile and reports success.
- All three produce a plausible-looking run rather than a failure, which is why
  every one of them needs an explicit read-back.

## Open questions

- Whether `LoadProfile` wedges identically when the blocking add-on is a
  *service* versus a *plugin* has not been isolated — the observed cases were
  services that would not stop.
- The `Addons33` schema number is Kodi-21-specific. Kodi 22 may renumber it;
  check the actual filename before assuming the path.
- Whether Kodi caches any part of a non-active profile's add-on state in memory,
  which would make a direct `Addons33.db` edit take effect late or not at all,
  has not been tested.

## See also

- [`kodi-process-control`](../kodi-process-control/SKILL.md) — restarting a
  wedged Kodi without leaving two running
- [`kodi-library-data`](../kodi-library-data/SKILL.md) — Kodi's other databases,
  and which operations destroy data
