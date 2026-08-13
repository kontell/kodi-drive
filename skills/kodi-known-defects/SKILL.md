---
name: kodi-known-defects
description: >
  Kodi and inputstream.adaptive defects confirmed by investigation, with their
  symptoms, upstream status, and how to recognise each from a log. Check here
  before spending hours on a bug that is not yours — particularly for whole-UI
  freezes on Kodi 22, audio that will not play in adaptive streams, and resume
  seeks that collapse to zero on live content.
license: CC-BY-SA-4.0
metadata:
  verified:
    kodi: ["22.0-BETA1 Piers", "21.3 Omega"]
    platform: ["Android TV", "Linux x86_64"]
    date: "2026-08-13"
    method: observed
---

# Confirmed upstream defects

Each entry below was traced to a cause in Kodi's own source, not merely observed.
**Check the linked issue before acting on any of them** — status changes, and a
skill that says "unfixed" after a merge is worse than no skill.

Status vocabulary: `unreported` · `filed` · `pr-open` · `merged`.

---

## CJobManager stops dispatching if any callback blocks

**Status: `pr-open`** — [xbmc/xbmc#28894](https://github.com/xbmc/xbmc/issues/28894),
fix in [#28944](https://github.com/xbmc/xbmc/pull/28944).
**Affects:** Kodi 22 (regression, introduced by commit `10e6892920`).
**Severity:** total UI freeze, unrecoverable without force-stop.

One JobWorker blocks inside a callback. `CJobManager::OnJobComplete` erases the
work item from `m_processing` **before** invoking callbacks, so a worker stuck in
one is invisible to the pool's accounting. The remaining workers age out at the
30-second idle timeout, leaving `m_workers = {wedged}` and `m_processing = {}`.

`StartWorkers()` then takes the wrong branch forever:

```cpp
if (m_processing.size() >= GetMaxWorkers(priority))  // 0 >= 4, false
  return;
if (m_processing.size() < m_workers.size())          // 0 < 1, TRUE
{
  m_jobEvent.Set();                                  // "a sleeping worker will take it"
  return;
}
m_workers.emplace_back(new CJobWorker(*this));       // never reached again
```

**No job submitted anywhere in Kodi ever runs again.** No log line, no error, no
recovery. Kodi 21 erased *after* the callback and correctly spawned a replacement.

The user-visible freeze arrives much later — **64 minutes** in the observed case —
when something finally waits on a job. Usually that is stopping playback:
`CVideoPlayer::~CVideoPlayer` ends in `while (m_outboundEvents->IsProcessing())
CThread::Sleep(10ms);`, and that loop can never exit.

**Recognise it in the log, an hour early:** four `Thread JobWorker terminating
(autodelete)` lines with one worker unaccounted for, and no `JobWorker start`
after. See [`kodi-freeze-diagnosis`](../kodi-freeze-diagnosis/SKILL.md).

**Do not be misled:** playback still starts and plays normally after the job
manager dies. Only the callbacks are gone. And the log keeps ticking, because
add-on services are `CThread`s rather than job workers.

---

## Unbounded channel count in the FFmpeg audio decoder

**Status: `unreported`.**
**Affects:** confirmed on 21.3; the code shape is long-standing.
**Severity:** SIGABRT, Kodi dies.

`CDVDAudioCodecFFmpeg::GetData` writes into a fixed `uint8_t* data[16]` stack
array with **no bounds check on the decoder's channel count**. Feed a decoder the
wrong codec and it reports a channel count that overruns the array, tripping the
stack protector: `__stack_chk_fail`, then SIGABRT.

Reachable whenever a stream is mislabelled — which the next entry makes easy.

---

## inputstream.adaptive has no MP3 or MP2 codec identity

**Status: `unreported`.**
**Severity:** audio silently plays as the wrong codec, or not at all.

Three separate gaps:

- The manifest path matches on an `mp4a` prefix, so **`mp4a.40.34` (MP3) and
  `mp4a.40.33` (MP2) are silently labelled AAC.**
- The TS demuxer maps PMT stream types `0x03` and `0x04` to the *video* names
  `mpeg1video` / `mpeg2video`.
- FLAC is unhandled everywhere. Opus and Vorbis work in DASH/fMP4 but not in TS.

**The fix is small, and the mechanism for it already exists.** Kodi resolves an
add-on's codec name with `avcodec_find_decoder_by_name()` and rejects unknown
names, so emitting valid FFmpeg names (`mp3`, `mp2`, `flac`) is sufficient.
`NAME_DTS = "dca"` in the existing code already proves the convention.

Note the interaction with the entry above: a stream mislabelled here is exactly
what hands the audio decoder the wrong codec.

---

## inputstream.adaptive clamps live seeks with no retry

**Status: `unreported`.**
**Severity:** resume on in-progress recordings silently starts at zero.

ISA clamps a seek to `GetMediaDurationMs()/1000 - m_liveDelay` and has **no
deferred or retry-seek mechanism**. A resume seek fired at open — when only ~48
seconds of playlist exists — collapses to zero and is never re-applied once more
of the stream is available.

`play_timeshift_buffer` does not help: it affects the *start* position, not the
clamp.

---

## PVR timer-type pre-selection ignores every usability flag

**Status: `unreported`.**
**Affects:** Omega and Piers.
**Severity:** a timer type that cannot work appears pre-selected.

`CPVRTimerType::GetFirstAvailableType` returns the add-on's first registered type
and nothing else (`xbmc/pvr/timers/PVRTimerType.cpp:106-118`):

```cpp
const std::vector<std::shared_ptr<CPVRTimerType>>& types = client->GetTimerTypes();
if (!types.empty())
  return *(types.begin());
```

It checks none of `REQUIRES_EPG_TAG_ON_CREATE`, `IS_READONLY` or
`FORBIDS_NEW_INSTANCES`. `GUIDialogPVRTimerSettings` then re-inserts the type it
had just filtered out of its own list, so adding a timer with no EPG context
offers an unusable type, already selected.

PVR add-ons work around it by ordering their types so the first is usable in
every context — which reads as a documented convention and is not one. See
[`kodi-pvr-addon`](../kodi-pvr-addon/SKILL.md).

---

## Kodi 21.3 against libpython3.14 segfaults on rapid add-on cycling

**Status: `unreported`.**
**Affects:** 21.3 built against libpython 3.14 — a pairing that postdates the
21.3 release, so this is a distribution build combination rather than one Kodi
ships. Whether the fault is in Kodi's teardown or in CPython 3.14 is open.

Segfault inside Kodi's own script teardown — `PyThreadState_Swap` reached via
`CPythonInvoker::onExecutionDone`, and `PyEval_RestoreThread`. Four occurrences
in one day of repeated cold resets.

Confirmed from a real crashlog:

```
Program terminated with signal SIGSEGV, Segmentation fault.
#0  ... in PyThreadState_Swap () from /usr/lib/.../libpython3.14.so.1.0
```

If you see that stack while cycling an add-on on and off, **stop looking at the
add-on**.

---

## Adding to this list

An entry belongs here only when the mechanism is traced to source, not merely
observed. A reproducible symptom with no identified cause is an
[issue](../../CONTRIBUTING.md), not an entry.

Every entry needs a status, and updating a status when upstream moves is as
valuable a contribution as adding one.

## Open questions

- The `CJobQueue` lock-order inversion suspected behind the CJobManager wedge was
  never proven — which queue instance the wedged thread waited on, and who held
  that mutex, was not recoverable from a retail Android device's thread dump.
  [#28948](https://github.com/xbmc/xbmc/issues/28948) covers a use-after-free in
  the same area, in the same code, and its relationship to this one is unestablished.
- The audio-decoder bounds bug has not been given a minimal reproducer, which is
  what filing it upstream would need.

## See also

- [`kodi-freeze-diagnosis`](../kodi-freeze-diagnosis/SKILL.md) — recognising the
  CJobManager signature before users do
- [`kodi-logs`](../kodi-logs/SKILL.md) — crashlogs and log signatures
- [`kodi-addon-driving`](../kodi-addon-driving/SKILL.md) — exercising an add-on
  to reproduce one of these
