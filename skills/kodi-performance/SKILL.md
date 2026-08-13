---
name: kodi-performance
description: >
  Make a Kodi add-on fast on the hardware people actually run it on. Use when
  something is slow on a TV box or stick but fine on your desktop, when a widget
  or listing lags, or before assuming a desktop measurement generalises. Covers
  the ~170x Python gap between a desktop and an ARM SoC, head-of-line blocking
  between unrelated work, and the import and API calls that cost whole seconds.
license: CC-BY-SA-4.0
metadata:
  verified:
    kodi: ["22.0-BETA1 Piers", "21.3 Omega"]
    platform: ["Android TV", "Linux x86_64"]
    date: "2026-08-13"
    method: observed
---

# Performance on real Kodi hardware

Most Kodi runs on an underpowered ARM box plugged into a television. Your desktop
is not a useful proxy for it, and the gap is far larger than intuition suggests.

## Measure the gap before trusting any desktop number

Identical Python work, same code, same database file, desktop versus an Android
TV box:

| Work | Desktop | Android TV box | Ratio |
|---|---|---|---|
| Digest 22,917 rows | 0.090 s | **15.3 s** | ~170x |
| Digest 6,751 rows | 0.039 s | **6.4 s** | ~164x |

That is not I/O and not lock contention — it was confirmed to be real query,
sort and hash work in the Python layer. **A 130 ms desktop operation becomes a
22 second one.**

Any design decision that reasons about "how long this takes" needs the ARM
number, not the desktop number. Several perfectly sound decisions in the case
above were sound *only* at desktop speed.

## The work is rarely where you think

In one investigation, new content took 30.8 seconds to appear in a widget. The
breakdown:

| Stage | Time |
|---|---|
| Deciding whether to refresh | **21.7 s** |
| The refresh itself | **12 ms** |

Nothing was broken, nothing was suppressed, and the data was correct the whole
time. **The cost was asking the question, not doing the work.**

This is why an end-to-end duration is a single reading that fits every theory.
Take intermediate timestamps — see [`kodi-jsonrpc`](../kodi-jsonrpc/SKILL.md).

## Head-of-line blocking between unrelated work

In the same case, 15.3 s of the 21.7 s was fingerprinting the **music** library,
which had nothing to do with the movie that had just been added. Two ordinary
decisions combined to cause it:

1. The loop iterated `sorted(databases)`, and `"music"` sorts before `"video"`.
2. Nothing was issued until the loop had a verdict for **every** candidate.

So the movie's refresh queued behind a full scan of an unrelated library. Without
music playing it would have completed 16 seconds sooner.

**Emit each result as soon as it is known**, rather than after the whole batch.
And where there is an obvious candidate — the thing that actually changed —
process it first.

## A fast path that declines is still a decision

The same system had a fast path designed to make new content visible
immediately. It early-returned, reasoning that the full refresh was "moments
away, and each refresh costs a scan".

That reasoning is correct at 130 ms. At 22 seconds it is wrong, and the fast
path silently never fires. **Any threshold reasoning of the form "the slow path
is nearly here" has to be evaluated at ARM speed.**

## Specific costs worth knowing

**`import requests` costs 1.11 s on Kodi 21 and 0.93 s on Kodi 22** inside Kodi's
embedded Python. Bytecode caching does not help — the cost is executing the
package's module bodies, and `.pyc` files were present on both. By comparison
`http.client`, `ssl`, `json` and `urllib` cost 0.000 s.

Keep `requests` in long-lived processes — a service, a sync stack — where the
import is paid once. **In the short-lived plugin process, use the stdlib.**

**`xbmcaddon.Addon()` costs ~2.9 ms.** Constructing one per list item accounted
for ~5 s of a 15 s listing. Build one and pass it, or read what you need once.

**Full-scan-and-hash in Python does not scale.** Where a gate needs a fingerprint
of a library, compute it in SQL as an aggregate, or maintain a checksum on write.
Materialising rows into Python tuples, sorting, `repr`-ing and hashing them is
O(library) per decision, and on ARM that is seconds every time.

## How to measure it properly

Take the measurement on the slow device, not on your desktop, and take
intermediates:

```sh
kodi-logtail mark
# trigger the operation
kodi-logtail since | grep -E 'your-addon-prefix'
```

Add a log line at each stage boundary in the code you are timing. Three
timestamps beat two, because two only tell you that time passed.

For process-level cost, see
[`kodi-process-control`](../kodi-process-control/SKILL.md) — and note that
sampling the wrong process reports a plausible ~1 MB, and Kodi's own footprint
dominates any absolute figure, so measure add-on cost as a delta.

## What fails silently

- A desktop benchmark passes and the feature is unusable on the target hardware.
- A fast path early-returns on reasoning that was true in development.
- Work queues behind unrelated work because of an incidental sort order.
- Nothing errors, nothing is logged, and the feature merely feels slow.

## Open questions

- The ~170x figure comes from one ARM SoC in a TV. Other Android TV hardware,
  and a Raspberry Pi, have not been measured — the order of magnitude is the
  useful part, not the exact number.
- Whether the Python gap is dominated by CPU, memory bandwidth, or Kodi's
  embedded interpreter build has not been isolated.

## See also

- [`kodi-jsonrpc`](../kodi-jsonrpc/SKILL.md) — timing stages instead of theorising
- [`kodi-process-control`](../kodi-process-control/SKILL.md) — measuring memory
  and CPU without measuring the wrapper
- [`kodi-test-rig`](../kodi-test-rig/SKILL.md) — getting the slow device to test on
