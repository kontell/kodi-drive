---
name: kodi-logs
description: >
  Read kodi.log usefully — turn on debug logging without the on-screen overlay,
  find the log on any platform, grep for the right severity, and read a crashlog.
  Use whenever you need to know what Kodi actually did, are about to reproduce a
  bug, or a user has reported a problem. Covers the lower-case severity trap that
  makes a naive error grep report every run clean.
license: CC-BY-SA-4.0
metadata:
  category: diagnosis
  verified-kodi: "21.3 Omega"
  verified-platform: "Linux x86_64"
  verified-date: "2026-08-13"
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
