---
name: kodi-addon-driving
description: >
  Install, enable, and exercise a Kodi add-on without navigating menus — fire
  plugin routes directly, send it service commands, change its settings, and
  simulate an offline server. Use when testing an add-on you are developing,
  reproducing a bug that takes a dozen keypresses to reach, or automating work
  that would otherwise mean answering confirmation dialogs by hand.
license: CC-BY-SA-4.0
metadata:
  category: python-addon
  verified-kodi: "21.3 Omega"
  verified-platform: "Linux x86_64"
  verified-date: "2026-08-13"
  verified-method: "observed"
---

# Driving an add-on headlessly

Most add-on behaviour is reachable without touching the UI. That matters because
UI navigation is blind, slow, and the main source of wasted cycles.

## Installing and enabling

An add-on dropped into `~/.kodi/addons/<id>/` needs a rescan, and it registers
**disabled**:

```sh
kodi-builtin 'UpdateLocalAddons()'
kodi-remote get Addons.SetAddonEnabled '{"addonid":"<id>","enabled":true}'
```

`Addons.SetAddonEnabled` has no profile argument — it acts on whichever profile
is loaded. See [`kodi-profiles`](../kodi-profiles/SKILL.md), where that silently
breaks isolation in an A/B comparison.

## Exercising a plugin directory

Test a plugin's directory listing without the UI at all:

```sh
kodi-remote get Files.GetDirectory '{"directory":"plugin://<id>/?mode=list"}'
```

Root listings of `library://music/` and `library://video/` return the same
items the home categories widget draws. Use that when the widget is missing
defaults — see [`kodi-library-nodes`](../kodi-library-nodes/SKILL.md).

A previous session saw `Files.GetDirectory` return 0 items for some
`library://` paths that still rendered in the UI. That case has not been
re-found; if you get an empty listing, screenshot before concluding the
path is empty.

You can at least skip the stepping. `GUI.ActivateWindow` takes a node path
directly, landing on it in one call:

```sh
kodi-remote get GUI.ActivateWindow \
  '{"window":"videos","parameters":["library://video/<addon>/<node>.xml/"]}'
```

## Firing a route directly

```sh
kodi-builtin 'RunPlugin(plugin://<id>/?mode=download&id=<item>)'
```

Where there is no EventServer — a remote or Android box — `Addons.ExecuteAddon`
is the JSON-RPC equivalent and takes the route's arguments as an object. The
builtin restriction covers builtins, not this:

```sh
kodi-remote get Addons.ExecuteAddon \
  '{"addonid":"<id>","params":{"mode":"download","id":"<item>"}}'
```

This reaches routes the UI would cost a dozen keypresses to get at, and it takes
ids the menu can only supply by having you focus the right row first.

**One piece of noise to ignore:** an *action* route fired this way always logs
`GetDirectory - Error getting plugin://…` plus `CGUIMediaWindow::GetDirectory(...)
failed`, because the route returns no listing. **The action still ran.** Grepping
the log for a failure right after the call will find that, and it means nothing.

## Service commands via NotifyAll

`JSONRPC.NotifyAll` reaches an add-on's `onNotification`. The payload is a
one-element JSON array — receivers conventionally read `json.loads(data)[0]`.

**The sender must be the add-on's exact sender constant, and a mismatch is
completely silent.** Receivers open with `if sender != <SENDER>: return`, so a
near miss — `kofin` for `plugin.video.kofin` — produces no log line, no error,
and a cheerful `"result":"OK"` from JSON-RPC.

That looks identical to "the add-on ignores NotifyAll". Acting on that reading
once meant answering twenty-odd confirmation dialogs by hand for work a loop
would have done.

Two rules follow:

1. **Read the constant out of the source** (`grep -rn 'SENDER' lib/`) rather than
   guessing it from the add-on id.
2. **Prove the channel with a control.** Send a deliberately invalid payload
   first and confirm the add-on logs its rejection. Silence means you never
   arrived; a rejection means you did.

Guarded messages are reachable too where the guard is a nonce the add-on keeps on
disk — read it and include it in the payload. That turns a sixteen-item cleanup
from sixteen dialog answers into a loop.

## Changing settings reliably

**Never edit a running add-on's `settings.xml`** — Kodi's in-memory copy can
clobber the file on save, and the file lies about the current value anyway (see
[`kodi-ui-navigation`](../kodi-ui-navigation/SKILL.md)).

The reliable cycle:

1. Disable the add-on — `Addons.SetAddonEnabled` false
2. Edit `addon_data/<id>/settings.xml` **in the active profile**
3. Enable again

A service add-on re-reads everything on the way up, which doubles as the bounce a
service-only code change needs anyway.

## Simulating an offline server

Point the add-on's server address at a non-routable address (`10.255.255.1`) via
that same settings cycle.

This scopes the outage to the add-on — no sudo, no firewall rules that would also
catch NFS or other services sharing the host — and connections fail with a clean
timeout rather than an instant refusal, which is what a real outage looks like.

## What fails silently

- A new add-on registers disabled; nothing tells you it did not start.
- `Files.GetDirectory` on a `library://` path whose node is not in the
  active profile tree returns `Invalid params.`, not the shipped file.
- A `NotifyAll` sender mismatch returns `"OK"` and does nothing.
- An action route logs a `GetDirectory` failure even when it succeeded.
- `SetAddonEnabled` acts on the loaded profile, not the one you meant.

## Open questions

- Why an earlier session saw `Files.GetDirectory` return 0 items for
  `library://` paths that still rendered has not been re-found. Root
  listings and one in-tree filter node returned items on 21.3.
- Whether the disable/edit/enable settings cycle is still required on Kodi 22,
  or whether the in-memory copy is flushed more eagerly there, is untested.

## See also

- [`kodi-profiles`](../kodi-profiles/SKILL.md) — which profile a change lands in
- [`kodi-jsonrpc`](../kodi-jsonrpc/SKILL.md) — asserting the result
- [`kodi-logs`](../kodi-logs/SKILL.md) — reading what the route actually did
- [`kodi-library-nodes`](../kodi-library-nodes/SKILL.md) — why a `library://`
  listing can be missing the shipped defaults
