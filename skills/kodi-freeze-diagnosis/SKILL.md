---
name: kodi-freeze-diagnosis
description: >
  Work out why Kodi froze, hung, or stopped responding — including getting native
  backtraces off an unrooted Android TV box. Use when the UI is unresponsive, Kodi
  will not quit, playback will not stop, or everything went slow with no error.
  Covers separating a C++ hang from a Python one, spotting GIL starvation, and the
  log signature that predicts a whole-UI freeze an hour before it happens.
license: CC-BY-SA-4.0
metadata:
  verified:
    kodi: ["22.0-BETA1 Piers", "21.3 Omega"]
    platform: ["Android TV", "Linux x86_64"]
    date: "2026-08-13"
    method: observed
---

# Diagnosing a frozen Kodi

A freeze is the hardest Kodi failure to work backwards from, because the log
usually keeps ticking. Background `CThread`s and Python services carry on writing
lines while the UI is dead, so **"the log looks alive" tells you nothing**.

Start by deciding which half is stuck.

## Is it C++ or Python?

These have completely different causes and completely different evidence.

**One grep separates them.** Count Python add-on log lines either side of the
suspected moment. In one case that ran **933 lines before, 0 after** — a
Python-wide freeze, with C++ entirely unaffected.

```sh
kodi-logtail grep '^\S+ \S+ .*(JELLYFIN|\[.*\])' | wc -l
```

| Python lines stop, C++ continues | a Python-side deadlock — often the GIL |
| C++ work stops, Python continues | a C++ hang — job system, a lock, a wait loop |
| Both stop | the app thread, or the process is gone |

An add-on whose logging is error-only proves nothing by its silence. **Anchor the
timing on a line that fires unconditionally on a fixed cadence** — a poll loop, a
periodic sync — so absence is meaningful.

## GIL starvation has a specific signature

If Python is stuck, check context switches rather than CPU:

```sh
grep voluntary_ctxt_switches /proc/<pid>/task/*/status
```

**Roughly 193 voluntary context switches per second across every Python thread is
GIL starvation**, not idle polling. The number is not arbitrary: CPython's default
`sys.setswitchinterval()` is 0.005 s, and 1/0.005 = 200. Threads waiting on the
GIL wake at that interval, fail to acquire, and sleep again.

The thread actually holding it is the one burning real CPU. One add-on's service
held the GIL and froze every other Python add-on on the box — and Kodi could not
shut down, because stopping a Python service requires the GIL.

**Sample CPU over minutes, not seconds.** A 61-second window read 91% where the
13-minute average was 24%. The short sample suggested a runaway spin and sent the
analysis the wrong way.

## Native backtraces on an unrooted Android TV box

This is possible, and it is the single most useful technique here. It was
initially recorded as impossible, which cost a whole investigation.

```sh
adb bugreport br.zip
unzip -o br.zip -d br
# then find the section: "------ VM TRACES JUST NOW ------"
```

`dumpstate` runs privileged and SIGQUITs every Java process, so that section
carries full **native** backtraces for every Kodi thread — 84 of them in the
observed case — symbolised for exported functions in `libkodi.so`.

The obvious routes do not work: `kill -3` from `adb shell` fails with *Operation
not permitted*, and `/data/anr/*` is `0600 system`.

**Caveat:** static and inlined functions render as `(???)`. That is enough to
block some questions — in the case above it prevented identifying which lock a
wedged thread was waiting on.

**Pull logcat immediately.** Its main ring buffer is *minutes* deep under D-pad
input spam, not hours. And turn Kodi's debug logging on *before* reproducing, or
you lose the `CServiceAddonManager: stopping <addon>` lines that name the
blocking add-on.

One Android shell trap: **Android uses mksh, where `r` is a reserved alias**
(`fc -e -`). Do not name a helper function `r`.

## The signature that predicts a whole-UI freeze

On Kodi 22 beta, `CJobManager` can die silently and the UI freezes **up to an
hour later**, when something finally waits on a job. The evidence is in the log
long before any symptom:

> **Four `Thread JobWorker terminating (autodelete)` lines with one worker
> unaccounted for, and no `JobWorker start` afterwards.**

```sh
kodi-logtail grep 'JobWorker (start|terminating)'
```

Once that pattern appears, a freeze is guaranteed at the next operation that
waits on a job — most often stopping playback, because `CVideoPlayer`'s
destructor ends in a sleep loop waiting for its event queue to drain.

Corroborating markers, all of which simply stop:

| Marker | Meaning |
|---|---|
| `DoWork - took ...ms to load` | texture jobs, gone |
| `CApplicationPlayerCallback::OnAVStarted` | playback callbacks, gone |

Playback still *starts* and plays after the job manager dies — only the callbacks
are missing. So "video plays fine" does not rule this out.

See [`kodi-known-defects`](../kodi-known-defects/SKILL.md) for the mechanism and
its upstream status. Recovery is a force-stop; nothing else clears it.

## What fails silently

- The log keeps ticking during a total UI freeze, because background threads are
  not job workers.
- The job manager dies with **no error line at all** — only an absence.
- A short CPU sample can read 4x the true average and invent a runaway spin.
- An error-only add-on log proves nothing by being quiet.

## Open questions

- The 193/s GIL figure follows from CPython's default switch interval, so an
  add-on that calls `sys.setswitchinterval()` would shift it. Not observed in
  practice, but worth knowing before treating the number as fixed.
- Whether the `VM TRACES JUST NOW` route works on all Android TV vendors, or
  depends on the OEM's `dumpstate`, has been confirmed on only one device.

## See also

- [`kodi-logs`](../kodi-logs/SKILL.md) — capturing the evidence, and crashlogs
- [`kodi-known-defects`](../kodi-known-defects/SKILL.md) — the CJobManager bug
- [`kodi-process-control`](../kodi-process-control/SKILL.md) — force-stopping and
  restarting cleanly
- [`kodi-adb`](../kodi-adb/SKILL.md) — the Android tooling this leans on
