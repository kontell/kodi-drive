# Pending observations

Real measurements with unproven mechanisms. **These are deliberately not skills** —
each has a symptom someone reproduced and a cause nobody established, which is
exactly what [CONTRIBUTING.md](../CONTRIBUTING.md) routes to an issue rather than a
pull request.

This file exists because the repository has no GitHub remote yet. **When it does,
each entry below should be filed using the
[Unverified observation](../.github/ISSUE_TEMPLATE/unverified-observation.yml)
template and deleted from here.** Keeping them in two places is how one copy goes
stale.

---

## 1. `stream_mode=timeshift` takes ~6 s to close a stream

**Observed.** `inputstream.ffmpegdirect` takes roughly **6 seconds** to close a
timeshifted stream, against about **0.1 s** with timeshift off. Reported that other
PVR add-ons close instantly even with multi-hour buffers.

**Not established.** The recorded hypothesis is that Kodi 21 does not call
`CloseLiveStream()` until after ffmpegdirect is destroyed, so the tuner cannot be
released early and ffmpegdirect waits out in-flight HTTP requests. Never confirmed.

**What would settle it:** instrument or log-trace the ordering of
`CloseLiveStream()` against ffmpegdirect's destructor on a stop, and compare
against a PVR add-on that closes instantly. If the ordering is as hypothesised,
this is an upstream issue rather than an add-on one.

Note the related, *confirmed* finding already in
[`kodi-pvr-addon`](../skills/kodi-pvr-addon/SKILL.md): under the stream-properties
path Kodi 21 does not call `CloseLiveStream()` on a normal stop at all. Whether
that is the same mechanism is precisely the open question.

---

## 2. Returning tempo to 1.0 triggers a keyframe re-seek

**Observed.** Restoring playback tempo to 1.0 causes a resync into a keyframe seek
on some builds, with inconsistent severity — an audio glitch, a video glitch, or a
full skip.

**Reported fixed in Kodi 22**, but not reproduced or re-verified here, and the
affected-build set was never characterised.

**What would settle it:** reproduce on Kodi 21 with a long-GOP source, then repeat
on 22 and confirm the difference. If it holds, it belongs in
[`kodi-known-defects`](../skills/kodi-known-defects/SKILL.md) with a `merged`
status rather than in
[`kodi-playback-tempo`](../skills/kodi-playback-tempo/SKILL.md) as an aside.

---

## Adding to this file

Only two things belong here: a symptom somebody actually observed, and a
statement of what would settle it. If you cannot write the second, it is not an
observation yet — it is a hunch, and it should stay out of the repository
entirely.
