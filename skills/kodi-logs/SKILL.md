---
name: kodi-logs
description: >
  Read kodi.log usefully — turn on debug logging without the on-screen overlay,
  find the log on any platform, grep for the right severity, and read a crashlog.
  Use whenever you need to know what Kodi actually did, are about to reproduce a
  bug, or a user has reported a problem. Covers the lower-case severity trap that
  makes a naive error grep report every run clean, and the duplicate filter that
  makes a count of log lines undercount what logged them.
license: CC-BY-SA-4.0
metadata:
  category: diagnosis
  verified-kodi: "21.3 Omega, 22.0 beta Piers, 22.0 RC1 Piers, 23.0-ALPHA1"
  verified-platform: "Linux x86_64"
  verified-date: "2026-08-27"
  verified-method: "observed"
---

# Reading kodi.log

`kodi.log` is where Kodi tells you what it did, and it is almost always the
fastest route to an answer. Two things make it hard: it is enormous, and grepping
it the obvious way finds nothing.

## Never read the whole file

On a busy box `kodi.log` runs to tens of megabytes and is almost entirely
irrelevant. Reading it whole burns an agent's context and buries the ten lines
that matter.

Mark, act, read what appeared:

```sh
kodi-logtail mark
kodi-remote reload
sleep 2
kodi-logtail errors
```

| Command | Gives you |
|---|---|
| `kodi-logtail mark` | records the current size as a marker |
| `kodi-logtail since` | everything written since the mark |
| `kodi-logtail errors` | Kodi's own error/warning lines since the mark |
| `kodi-logtail addon-errors` | add-on tracebacks and `ERROR::` lines |
| `kodi-logtail grep <re>` | a targeted search since the mark |
| `kodi-logtail tail [N]` | the last N lines, ignoring the mark |

Kodi rotates `kodi.log` to `kodi.old.log` on start, so a log that shrank means a
restart happened. `kodi-logtail` detects this and reads from the top rather than
silently returning nothing.

A wait loop that polls a fixed window (`tail -c 100000 kodi.log | grep …`)
instead of reading since the mark misses the line the moment enough debug
output follows it — a busy sync writes 100 KB in seconds. Observed: a bounded
wait for `Full sync completed` ran its full 800 s against a line that had
already scrolled past. Mark first, then read from the mark, every time.

## Severities are lower-case, and a grep for ERROR finds nothing

**This is the trap that matters most.** Kodi 21 writes its severity field in
lower case:

```
2026-08-13 10:10:16.903 T:2593245 warning <general>: CAddonMgr::FindAddons: ...
```

Measured on a real 21.3 log: **197 `warning` and 26 `error` lines, and zero
uppercase severity matches.** A script grepping `" ERROR "` reports a clean run
every single time, for every arm of a comparison, and looks like good news.

Worse, an unauthored uppercase grep is not merely empty — it is *wrong*. On that
same log it returned exactly two hits, both of which were add-ons logging their
own level inside the message body of an `info` line:

```
... info <general>: JELLYFIN.__main__ -> ERROR::service.py:43 ExitService
```

So the naive pattern found 2 false positives and missed all 220 real ones.

Anchor on the `<component>` field that follows the severity:

```sh
grep -iE '[[:space:]](error|warning|fatal|severe)[[:space:]]+<' kodi.log
```

`kodi-logtail errors` does this. Use `kodi-logtail addon-errors` for the
add-on-level severities, which live in the message body and *are* uppercase by
convention.

## Identical lines are collapsed, so a line count is not an event count

Kodi writes `kodi.log` through spdlog's `dup_filter_sink` with a 10 s window
(sourced: `xbmc/utils/log.cpp`, lines 122–128 at `21.3-Omega`, 169–175 on
master `9abafab`). A line whose text matches the last line written, less than
10 s after it, is dropped, and the next line written is preceded by the number
dropped. Five identical `xbmc.log` calls and then a different one, on 22.0 RC1
and 23.0-ALPHA1:

```
info <general>: dupcheck: same line
info <general>: Skipped 4 duplicate messages..
info <general>: dupcheck: different line
```

**A count of lines undercounts whatever logged them** — retries, requests,
failed rows. Add the `Skipped N` figures, or count from something other than
the log.

- **Only the message text is compared**, not the thread, the `<component>` or
  the level (sourced: `filter_` in spdlog's `sinks/dup_filter_sink.h`). Any
  other line written in between, from any thread, ends the run.
- **A run that goes on is written again once 10 s have passed.** The window
  runs from the last copy written. The same line logged every 4 s, with nothing
  else logging, was written every third time, each copy preceded by
  `Skipped 2 duplicate messages..`.
- **The notice belongs to the line that ends the run, not to the dropped
  ones.** It carries that line's thread and `<component>` (sourced: the notice
  is built from the next message's `logger_name`). Three identical warnings
  from one thread, then a line from another:

  ```
  T:133   warning <general>: dupcheck: warned
  T:134   warning <general>: Skipped 2 duplicate messages..
  T:134      info <general>: dupcheck: from another thread
  ```

  A grep for one add-on's `<component>` misses the count of its own dropped
  lines, and picks up counts that belong to others.
- **The notice's level depends on the spdlog build.** spdlog 1.17.0, which
  master's `tools/depends` pin and the two builds above link, gives it the
  dropped lines' level, as shown. spdlog 1.10.0, which `21.3-Omega`'s depends
  pin, writes it at `info` (sourced: `dup_filter_sink.h` at spdlog `v1.10.0`),
  so the severity grep above does not see that errors were dropped at all.
  Linux distribution builds link the system spdlog.
- **Android's logcat gets every line.** Only the file sink sits behind the
  filter; the platform sinks are added beside it (sourced: `m_platform->AddSinks`
  in `xbmc/utils/log.cpp`, and `AndroidInterfaceForCLog.cpp`, which adds
  spdlog's `android_sink`). When a count matters on Android, `adb logcat` has
  the lines `kodi.log` dropped.

## Turning debug logging on

Three routes, in increasing order of usefulness for automation:

**In the UI** — Settings > System > Logging > "Enable debug logging". This also
turns on a large on-screen overlay, which ruins screenshots.

**Without the overlay** — put this in
`~/.kodi/userdata/advancedsettings.xml` and restart Kodi:

```xml
<advancedsettings>
  <loglevel hide="true">1</loglevel>
</advancedsettings>
```

**Over JSON-RPC, on 21** — `Settings.SetSettingValue` with
`{"setting":"debug.showloginfo","value":true}` answers `true` and takes effect
at once (overlay included). **On 22 that setting id is gone:**
`Settings.GetSettingValue` for `debug.showloginfo` returns `-32602 Invalid
params`, and `Settings.GetSettings` for the `system`/`logging` category at
`expert` level lists only `debug.extralogging`, `debug.setextraloglevel`,
`debug.screenshotpath` and the three `eventlog.*` ids (22.0 beta,
`20260825-ab5284f`). Whether a 22 box logs at debug level is read off the log
itself — the `debug <general>` lines — not off a setting.

**A profile switch can turn it back off.** Each profile has its own
`guisettings.xml`; re-entering a profile that was created with logging off
comes back with it off, and a request count taken afterwards reads zero.
Check the setting (21) or the log (22) every time a profile changes hands,
before counting anything.

**Turn it on before you reproduce, not after.** With it off you lose the
`CServiceAddonManager: stopping <addon>` lines that name which add-on blocked a
shutdown — which is often the whole answer.

## Where the log lives

| Platform | Path |
|---|---|
| Linux | `~/.kodi/temp/kodi.log` |
| macOS | `~/Library/Logs/kodi.log` |
| Windows | `%APPDATA%\Kodi\kodi.log` |
| Android | `/sdcard/Android/data/org.xbmc.kodi/files/.kodi/temp/kodi.log` |

`kodi-logtail` picks the right default per platform. For Android, reach it over
ADB — see [`kodi-adb`](../kodi-adb/SKILL.md).

## Crashlogs

Kodi writes `kodi_crashlog-*.log` to the home directory on a hard crash. The
signature is near the top:

```sh
grep -m1 -A3 "Program terminated" ~/kodi_crashlog-*.log
```

One concrete example worth recognising, because it is not an add-on bug: **Kodi
21.3 built against libpython3.14 segfaults under rapid add-on start/stop
cycling**, always inside its own script teardown — `PyThreadState_Swap` reached
via `CPythonInvoker::onExecutionDone`, and `PyEval_RestoreThread`. Four
occurrences in one day of repeated cold resets. If you see that stack while
cycling an add-on, stop looking at the add-on.

## Credentials in logs

**Any log excerpt is credential-bearing until proven otherwise.** Kodi core and
`inputstream.adaptive` write full stream URLs — including `api_key=` and `token=`
query parameters — at debug level, and an add-on cannot prevent it.

Redact before pasting a log anywhere: an issue, a PR, a chat message, or a skill
in this repo. `scripts/scrub.py --detect` will catch the common shapes.

## Open questions

- The lower-case severity field was confirmed on 21.3. Which release changed it
  from the older uppercase form has not been established, so the anchored
  case-insensitive pattern is deliberately used rather than assuming either case.
- `<loglevel hide="true">` suppresses the overlay on 21.3; whether the attribute
  is still honoured in 22 has not been checked.

## See also

- [`kodi-process-control`](../kodi-process-control/SKILL.md) — restarting cleanly
  so the log rotation means what you think
- [`kodi-connect`](../kodi-connect/SKILL.md) — getting access to the box in the
  first place
