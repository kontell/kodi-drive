---
name: kodi-jsonrpc
description: >
  Use Kodi's JSON-RPC API as ground truth instead of guessing from screenshots.
  Use when asserting that a change landed, testing playback without watching it,
  or checking whether an API you plan to call actually exists. Covers
  JSONRPC.Introspect and its limits, the JSON-RPC/Python API divergence that
  compiles and then fails in front of the user, and the several readings that
  agree with whatever you hoped.
license: CC-BY-SA-4.0
metadata:
  category: access
  verified-kodi: "21.3 Omega"
  verified-platform: "Linux x86_64"
  verified-date: "2026-08-13"
  verified-method: "observed"
---

# JSON-RPC as ground truth

Screenshots prove rendering. JSON-RPC proves state. A screenshot shows what was
drawn; it does not show what was written. If a change has any state behind it,
query it.

```sh
kodi-remote get Application.GetProperties '{"properties":["version","name"]}'
kodi-remote get Player.GetActivePlayers
kodi-remote get GUI.GetProperties '{"properties":["currentwindow"]}'
```

A `*.GetProperties` call with no `properties` argument returns `null` rather than
erroring — which reads as "no data" instead of "you forgot the argument".

## Introspect first, but do not trust it too far

`JSONRPC.Introspect` lists every available method. Check it before assuming an
API exists — Kodi's PVR surface, for instance, is read-only except for timers:
there is no `SetRecordingPlayCount` and no delete-recording call.

```sh
kodi-remote get JSONRPC.Introspect
```

**But JSON-RPC is not the Python API, and Introspect will happily confirm
something you cannot then call from an add-on.** The two namespaces overlap
without matching:

| JSON-RPC | Python |
|---|---|
| `Player.AddSubtitle` | *does not exist* |
| — | `Player.setSubtitles(path)` |

An add-on written straight off an Introspect result compiles, passes its unit
tests against a fake, and dies on `AttributeError` in front of the user.

Use both halves in order. Drive JSON-RPC first to prove the **mechanism** — it
needs no build, no install, and no bounce, so a player behaviour can be settled
in one call before any add-on code exists. Then look the Python name up
separately before building on it:

```sh
python3 -c "import xbmc; print([m for m in dir(xbmc.Player) if 'ubtitle' in m])"
```

against Kodistubs. Worth doing in the unit tests too — a fake player answers to
whatever you call it, so assert names against `xbmc.*` rather than your own
double.

## Testing playback without watching it

`Player.Open` takes library ids, `Player.Seek` takes a time or percentage, and
`Player.GetProperties` is the assertion:

```sh
kodi-remote get Player.Open '{"item":{"episodeid":123},"options":{"resume":true}}'
kodi-remote get Player.GetProperties '{"playerid":1,"properties":["time","totaltime","percentage"]}'
```

`options.resume` works for library ids. Seeks land keyframe-snapped a second or
two off the target — assert with tolerance.

## Three readings that agree with whatever you hoped

**Infolabels go stale, they do not go empty.** `XBMC.GetInfoLabels` on
`MusicPlayer.*` / `VideoPlayer.*` keeps returning the *previous* item's values
after playback stops, and a short item can finish before you read it. A reading
taken a beat too late is silently the old one.

Assert `Player.GetItem` returns the item you opened before trusting any
infolabel, and pick something long enough to still be playing. A codec comparison
once read as "both tracks identical" purely because the second had already ended;
the control only worked once the track was minutes long.

**`speed: 1` means "not paused", not "playing".** Testing an HLS stream with a
subtitle rendition, `Player.GetProperties` returned the subtitle track,
`subtitleenabled: true` and `speed: 1`, the log created an ASS track, and
`Player.Open` answered `OK` — while the screen stayed black at 0:00 for over two
minutes.

The only signal separating a running playback from a wedged one is **`time`
sampled twice**. A single reading agrees with whatever you hoped. This is cheap
to fold into any playback assertion and is the difference between ruling an
approach out and shipping it.

**An end-to-end duration is a single reading too.** It tells you *that* thirty
seconds went somewhere, and every plausible story fits it equally well. Find an
intermediate the system already prints and take three timestamps instead of two.

Worked case: "a queued download takes 30 s to start" supported a tidy theory
about a shared wake Event. The theory was right about a real bug, the fix was
correct, and the measurement afterwards was **unchanged** — the actual delay was
elsewhere. Three timestamps settled it in one trial: request at 21:22:30.2, the
add-on's own "download queued" log line at 21:22:31.8, the row going active at
21:23:02.7. 1.6 s to enqueue, 31 s to claim. Only the second half was worth
looking at.

## When you do need pixels, aim at them

Anything transient is a target you have to aim at. Do not shoot blind at a moment
you guessed — find the longest-lived instance and seek into the middle of it. For
subtitles that means parsing the `.srt` for the longest-duration cue and seeking
there, which turns four wasted screenshot cycles into one shot that lands.

**A notification fits about 33 characters and scrolls the rest.** A screenshot
captures an arbitrary window into a long message, and that window can say
something the whole string does not. Measured: `Not enough free space: 5.7 GB
needed, 4.2 GB free` was caught mid-scroll as `enough free space: 5.7 GB
needed,` — the opposite meaning, from correct code.

Two consequences. Reading a toast off a screenshot settles only what a *user*
sees at a glance, so check the string in the source before calling the text
wrong. And when it is the user's glance you care about, ~33 characters is a
design limit: a message that has to scroll to make sense is a message to shorten.

## What fails silently

- `*.GetProperties` with no arguments returns `null`, not an error.
- Introspect confirms methods the Python API does not have.
- Infolabels return the previous item rather than nothing.
- `speed: 1` reports a wedged player as a healthy one.
- A single `time` reading, or a single end-to-end duration, confirms any theory.

## Open questions

- Whether `options.resume` works for anything other than library ids has not been
  tested here; a bare `plugin://` path is reported elsewhere as unable to resume.
- The 33-character notification limit was measured on one skin at 1280x720 and is
  font- and resolution-dependent. Treat it as an order of magnitude.

## See also

- [`kodi-connect`](../kodi-connect/SKILL.md) — getting a working target first
- [`kodi-library-data`](../kodi-library-data/SKILL.md) — the databases behind the
  API, when JSON-RPC will not tell you
- [`kodi-ui-navigation`](../kodi-ui-navigation/SKILL.md) — driving the UI itself
