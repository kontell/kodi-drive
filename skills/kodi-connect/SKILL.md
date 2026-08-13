---
name: kodi-connect
description: >
  Find a Kodi on the network and get control of it — JSON-RPC, EventServer, ADB,
  or SSH — and store its address and credentials safely. Use this FIRST whenever
  you need to see or change real Kodi behaviour and do not already have a working
  target, including when a user reports a problem and you have no access yet.
  Covers discovering instances automatically, turning on the APIs that are off by
  default, and walking a user through granting access on a TV with only a remote.
license: CC-BY-SA-4.0
metadata:
  category: access
  verified-kodi: "21.3 Omega"
  verified-platform: "Linux x86_64"
  verified-date: "2026-08-13"
  verified-method: "observed"
---

# Getting control of a Kodi

You cannot reason your way to correct Kodi behaviour. Reload the skin and look;
query the state and read it back. Everything else in this repo assumes you have a
Kodi you can drive, and this skill is how you get one.

**Do not skip this and guess.** If you have no access, ask the user for it — that
is a one-minute conversation, and the alternative is a confident wrong answer.

## 1. Look before you ask

Run this first, always:

```sh
kodi-discover                 # human-readable table
kodi-discover --json          # machine-readable
kodi-discover --no-scan       # skip the port sweep (faster, less thorough)
kodi-discover --subnet 192.0.2.0/24
```

It tries mDNS, ADB, SSDP, then a port sweep of the local `/24`, and confirms every
candidate with a real `JSONRPC.Ping` before reporting it. A full sweep takes about
six seconds.

```
HOST             PORT   VERSION    NAME           VIA     STATUS
127.0.0.1        8080   21.3       Kodi           local   ok
192.0.2.10       8080   21.3       Kodi           sweep   ok
```

Now you can ask a question the user can actually answer — *"I found Kodi 21.3 at
192.0.2.10, is that the one you're having trouble with?"* — instead of asking for
an IP address they do not know.

A row with status `unreachable` answered discovery but refused JSON-RPC. That is
a real Kodi with its API off; go to [section 3](#3-turning-the-apis-on).

## 2. Store the target

Never put a host, port, or credential in a repo, a `CLAUDE.md`, or your terminal
output. Put it in `~/.config/kodi-drive/targets.env`, mode `0600`:

```sh
mkdir -p ~/.config/kodi-drive && chmod 700 ~/.config/kodi-drive
cat >> ~/.config/kodi-drive/targets.env <<'EOF'
KODI_TARGET_DEFAULT=devbox
KODI_DEVBOX_HOST=192.0.2.10
KODI_DEVBOX_PORT=8080
KODI_DEVBOX_USER=kodi
KODI_DEVBOX_PASS=...
EOF
chmod 600 ~/.config/kodi-drive/targets.env
```

Every `kodi-*` helper reads this. Switch targets with `KODI_TARGET=tv kodi-remote home`.

**Never `cat` this file.** Agent session transcripts record everything printed to
the terminal, and they are not scrubbed. Read it into the environment, never onto
your screen.

## 3. Turning the APIs on

All of these are **off by default**, which is the single most common reason
discovery finds nothing. Ask the user to set them:

| Setting | Path | Needed for |
|---|---|---|
| Allow remote control via HTTP | Settings > Services > Control | everything (port 8080) |
| Allow programs on other systems to control Kodi | Settings > Services > Control | `kodi-builtin` (EventServer, UDP 9777) |
| Announce services to other systems | Settings > Services > General | mDNS discovery |

Settings level must be **Standard** or higher, or the Services section is hidden.
Toggle it with the gear icon at the bottom-left of the settings screen.

Both control settings live behind "Allow remote control via HTTP" being on — the
rest of the section stays greyed out until it is.

### On a TV, with only a remote

Talk the user through it by direction, not by mouse position:

> From the home screen: go **up** to the gear icon and press OK, then **Services**,
> then **Control** in the left column. Turn on *Allow remote control via HTTP*.
> Set a username and password while you are there. Then turn on *Allow programs
> on other systems to control Kodi* just below it.

Then re-run `kodi-discover`.

## 4. The three transports

**JSON-RPC over HTTP** — the workhorse. Reads state, drives navigation, changes
settings. Use `kodi-remote`. This is the one you want.

**EventServer (UDP 9777)** — the only remote route to Kodi *builtins*.
`Input.ExecuteAction` accepts a fixed enum of action names, so there is no
JSON-RPC path to `ReloadSkin()`, `ActivateWindow(...)`, or `Skin.SetString(...)`.
Use `kodi-builtin`.

It is fire-and-forget UDP: no response, no acknowledgement, and **no error if
Kodi rejects the builtin or is not listening**. Always confirm the effect:

```sh
kodi-builtin 'ActivateWindow(Settings)'
sleep 1
kodi-remote get GUI.GetProperties '{"properties":["currentwindow"]}'
```

**ADB** — Android and Android TV. Needed for logs, installs, and anything
Android-specific. See the `kodi-adb` skill.

**SSH** — when you need the filesystem: `advancedsettings.xml`, userdata,
`kodi.log` on a box you cannot mount. Set `KODI_<NAME>_TRANSPORT=ssh` and
`KODI_<NAME>_ADDR=user@host`.

## 5. Confirm you have control

```sh
kodi-remote get Application.GetProperties '{"properties":["version","name"]}'
```

A `*.GetProperties` call with no `properties` argument returns `null` rather than
erroring — which reads as "no data" instead of "you forgot the argument". Always
pass them. Discover what a method accepts with:

```sh
kodi-remote get JSONRPC.Introspect
```

## What fails silently

- **A 401 looks like nothing at all.** An unauthenticated probe against a
  password-protected Kodi returns HTTP 401, and `curl -f` treats that as failure.
  Scanning with `curl -f` therefore misses every Kodi configured the way Kodi
  itself recommends. `kodi-discover` accepts 200 *and* 401 for this reason.
- **The EventServer never reports failure.** A wrong builtin name, a disabled
  service, a wrong port — all identical to success from the sender's side.
- **`Application.GetProperties` with no arguments returns `null`**, not an error.
- **Kodi may answer on the LAN address but not loopback, or vice versa**, depending
  on binding and firewall. Discovery reports each address separately; if one fails,
  try the other before concluding the API is off.

## Open questions

- `dns-sd` (macOS) is detected but skipped — its non-interactive browsing did not
  return usable output in testing. Someone on macOS should confirm whether
  `dns-sd -B _xbmc-jsonrpc-h._tcp` can be made to work in a script, or whether
  `dns-sd -Z` is the better route.
- The SSDP path has not been verified against a Kodi with its UPnP renderer
  enabled — the test instance had it off, so that branch returned nothing rather
  than being confirmed working.
- Android 11+ wireless debugging advertises `_adb-tls-connect._tcp` over mDNS with
  a rotating port. `kodi-discover` reports already-connected ADB devices but does
  not yet browse for that service.

## See also

- `kodi-adb` — Android and Android TV specifics
- `kodi-logs` — getting a log once you have access
- `kodi-triage` — the debugging entry point, which starts here
