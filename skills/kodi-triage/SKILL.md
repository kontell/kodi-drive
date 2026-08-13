---
name: kodi-triage
description: >
  Turn a vague Kodi complaint into a diagnosis. Use this the moment someone says
  Kodi is broken, slow, crashing, freezing, not playing something, or "not working"
  — including when they give you almost nothing to go on. Walks from no access and
  no information through getting hands on the box, capturing a log of the actual
  failure, and isolating a bad add-on in a clean profile before theorising about
  causes.
license: CC-BY-SA-4.0
metadata:
  category: orientation
  verified-kodi: "21.3 Omega"
  verified-platform: "Linux x86_64, Android TV"
  verified-date: "2026-08-13"
  verified-method: "observed"
---

# Triaging a broken Kodi

You have been handed something like *"Kodi no work good, need help."* That is a
normal starting point, not an unreasonable one. Work the ladder below in order.

**The single rule that matters: ask for what you need instead of making do.**
Most bad Kodi debugging is an agent reasoning at length from a screenshot and a
guess because asking for device access felt like an imposition. It is not. One
question costs a minute; a confident wrong answer costs the user an afternoon and
sends them down the wrong path.

---

## Step 0 — Do not theorise yet

Resist the first plausible cause. Kodi has an unusually large number of failure
modes that present identically: a bad add-on, a corrupt database, a skin that
cannot render, a dead network share, an out-of-date binary add-on, and a genuine
Kodi bug all look like "it hangs on startup".

Ask two questions while you set up access, because the answers narrow the search
enormously:

- **What changed?** New add-on, update, new skin, new device, moved house? Kodi
  rarely breaks spontaneously.
- **What exactly happens, and when?** "Crashes" and "freezes" are different
  problems. Startup, playback, or navigation are different problems.

## Step 1 — Find the Kodi before asking for its address

Run this first. Do not open by asking for an IP address, which most users cannot
answer:

```sh
kodi-discover
```

It sweeps mDNS, ADB, SSDP, then the local subnet, and confirms each hit with a
real `JSONRPC.Ping`. Now you can ask something answerable:

> "I found a Kodi 21.3 at 192.0.2.10 — is that the one giving you trouble?"

If nothing is found, that is usually because Kodi's API is off rather than absent.
[`kodi-connect`](../kodi-connect/SKILL.md) has the settings to turn on and the
words to walk someone through it on a TV with only a remote.

## Step 2 — Get access, and say why you want it

Offer the ladder and let them pick whatever is easiest:

| Access | Gets you |
|---|---|
| Kodi on your machine | everything, fastest loop |
| JSON-RPC over the network | state, navigation, settings |
| ADB (Android TV, stick, phone) | all of the above plus logs and installs |
| SSH to the box | the filesystem: `advancedsettings.xml`, userdata, logs |
| "I'll paste a log" | workable, but every question costs a round trip |

**If none is available, say plainly what you can and cannot conclude without it,
then work from pasted logs.** Do not silently downgrade to guessing.

## Step 3 — Turn debug logging on *before* reproducing

This is the step most often skipped, and skipping it costs a whole reproduction
cycle. With debug logging off you lose the lines that name the culprit — notably
`CServiceAddonManager: stopping <addon>`, which is frequently the entire answer.

Prefer `advancedsettings.xml` over the UI toggle, because the UI toggle also
raises a large on-screen overlay that ruins every screenshot:

```xml
<advancedsettings>
  <loglevel hide="true">1</loglevel>
</advancedsettings>
```

Restart, then reproduce. See [`kodi-logs`](../kodi-logs/SKILL.md).

## Step 4 — Capture the failure, not the whole log

```sh
kodi-logtail mark
# have the user reproduce the problem now
kodi-logtail errors
kodi-logtail addon-errors
```

**Never read the whole file.** It is tens of megabytes of noise around the ten
lines that matter.

Two traps that will otherwise waste the step:

- **Kodi 21 writes severities in lower case.** A grep for `ERROR` finds nothing
  and reports a clean run. `kodi-logtail errors` handles this; a hand-rolled grep
  will not.
- **Logs carry credentials.** Kodi and `inputstream.adaptive` write full stream
  URLs including `api_key=` at debug level. Redact before pasting anything
  anywhere, including into your own reply.

If Kodi crashed rather than misbehaved, go straight to the crashlog:

```sh
grep -m1 -A5 "Program terminated" ~/kodi_crashlog-*.log
```

## Step 5 — Suspect the add-ons, and prove it with a clean profile

**Most "Kodi is broken" is one bad add-on.** Many users have accumulated a large
number of them, often from unofficial sources, and one misbehaving service can
take down far more than itself — a single add-on holding the Python GIL has been
observed to freeze *every other Python add-on on the box* while C++ carried on
normally, leaving Kodi unable even to shut down.

Do not try to reason about which one. Bisect:

1. Create a fresh profile and reproduce there with nothing installed.
2. **Reproduces on a clean profile?** It is not an add-on. Go to Step 6.
3. **Does not reproduce?** It is an add-on. Add them back in halves until it
   returns.

[`kodi-clean-profile`](../kodi-clean-profile/SKILL.md) has the mechanics, and it
matters that you read it first — `Profiles.LoadProfile` returns `"OK"` for
switches that never happen, and `Addons.SetAddonEnabled` applies to whichever
profile is loaded, which quietly ruins the isolation you are trying to build.

## Step 6 — Narrow to a subsystem

With add-ons ruled out, use the symptom:

| Symptom | Look at |
|---|---|
| Hangs at startup, or on quit | a service add-on that will not stop; check for `waiting on thread` |
| Whole UI freezes, unrecoverable | a blocked callback; check for repeated `Thread JobWorker terminating` with no `JobWorker start` after |
| Library empty or wrong | the databases — see [`kodi-library-data`](../kodi-library-data/SKILL.md) |
| Playback fails or plays wrong track | stream and player selection; sample `time` twice before believing it is playing |
| Artwork missing or slow | the texture cache |
| Skin renders wrong or partially | a dropped include — Kodi logs a parse error and renders without it |
| Crash with no message | the crashlog, not kodi.log |

## Step 7 — Reproduce it yourself before fixing it

If you have access, reproduce the failure on a Kodi you control. A fix verified
only against a description is not verified.

---

## Things that will mislead you

- **A screenshot of a working-looking UI proves nothing** about state. Query it.
- **`speed: 1` does not mean playing.** Sample `time` twice.
- **A settings value read from `settings.xml` can be days stale.** Read it back
  through the add-on.
- **An action route always logs a `GetDirectory` error**, even when it worked.
  Do not report that as the fault.
- **A JSON-RPC call against a stopped Kodi hangs rather than refusing**, which
  reads like a wedged box rather than an absent one.

## Open questions

- The symptom-to-subsystem table above is seeded from a handful of real
  investigations rather than a systematic sweep of Kodi's issue tracker. Treat it
  as a starting point, and add rows as cases are confirmed.

## See also

- [`kodi-connect`](../kodi-connect/SKILL.md) — getting access, step 1 and 2
- [`kodi-logs`](../kodi-logs/SKILL.md) — capturing and reading the evidence
- [`kodi-clean-profile`](../kodi-clean-profile/SKILL.md) — the bisect
- [`kodi-test-rig`](../kodi-test-rig/SKILL.md) — a throwaway Kodi to reproduce on
