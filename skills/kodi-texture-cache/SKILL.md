---
name: kodi-texture-cache
description: >
  Serve artwork Kodi caches efficiently, and understand when caching saves nothing
  at all. Use when choosing an image format for an add-on, when artwork is slow to
  load or missing, when folder art is ignored, or before seeding the texture cache
  directly. Covers the alpha-channel rule that silently doubles your storage cost,
  and the extension-based decoding that differs between Kodi versions.
license: CC-BY-SA-4.0
metadata:
  category: kodi-data
  verified-kodi: "21.3 Omega, 22.0b1 Piers"
  verified-platform: "Linux x86_64"
  verified-date: "2026-08-13"
  verified-method: "observed"
---

# Kodi's texture cache

Kodi caches remote artwork locally and re-encodes it. Whether that re-encoding
helps depends on one property of your source image, and getting it wrong costs
you twice with no error.

## The alpha rule

**Kodi re-encodes a cached texture to JPEG only when the source carries no alpha
channel.** Any RGBA source is written back as a **PNG of the same dimensions**,
at the same 1080 cap — so the cache saves nothing at all.

Measured on a 1920×1080 splashscreen:

| Source | On disk | Cached |
|---|---|---|
| RGBA PNG | 3.6 MB | 3.6 MB PNG |
| WebP (lossy) | 698 KB | 600 KB JPEG |

If your artwork does not need transparency, **do not ship it with an alpha
channel**. Strip it at the source.

## Three traps that revert the win while still rendering perfectly

- **`format=Jpg` from a media server** can serve a stale derivative that ignores
  every other cache-key parameter — so you get an image, it looks right, and it
  is not the one you asked for.
- **Lossless WebP is ARGB in the bitstream**, so it reads as having alpha and
  goes straight back onto the PNG path. Lossy WebP is the one that helps.
- **WebP bytes under a `.png` filename**: Omega refuses outright (HTTP 500 from
  Kodi's own image endpoint), while Piers happens to sniff the content and
  succeeds. Neither version's `AddonInfoBuilder` validates the extension, so this
  is silently version-dependent.

The last one matters because **Kodi picks the decoder from the file extension for
local files**. The extension is a decoding instruction, not a label.

## Verifying decode behaviour without guessing

Kodi's own web server exposes an `/image/` endpoint that runs the real decoder,
so you can test what Kodi will actually do with a URL:

```sh
curl -s -o /dev/null -w '%{http_code}\n' \
  -u "$KODI_USER:$KODI_PASS" \
  "http://$KODI_HOST:$KODI_PORT/image/$(python3 -c '
import sys,urllib.parse; print(urllib.parse.quote(sys.argv[1],safe=""))' \
  "image://https%3a%2f%2fexample.com%2fart.png/")"
```

A 500 means the decoder rejected it. That is a real answer, obtained in one call,
rather than an inference from a blank tile.

## Folder art is matched by name, not by content

Kodi reads a folder's art from **`folder.jpg`, by name**. `folder.png` is
ignored entirely.

The bytes, however, may be PNG — and often must be, since a real JPEG loses the
icon's alpha. So the correct artefact is frequently *PNG data in a file called
`folder.jpg`*, which looks like a mistake and is not.

A `.tbn` file beside an individual `.xsp` or `.m3u8` does nothing.

## Seeding the cache directly

The cache **can** be pre-populated, and special-type images are never
hash-revalidated — `ShouldCheckForChanges` marks them not updateable, so an entry
seeded with empty `imagehash` and `lasthashcheck` is served indefinitely.

Two requirements that are easy to miss:

- **The `sizes` row with `size=1` is mandatory** — the lookup is an INNER JOIN,
  so an entry without it is invisible rather than broken.
- The cache filename hash is **CRC-32/MPEG-2 over the lower-cased key**. Not the
  common CRC-32.

**The cache key must match Kodi's byte for byte**, and it differs by version.
Chapter thumbnails, for instance:

| Kodi | Key form |
|---|---|
| Omega | raw `chapter://{dynPath}/{n}` |
| Piers | `image://video@{urlencoded}/?chapter={n}`, **lower-case** percent-hex |

A key that is right except for hex case produces blank tiles and no error.

The database also differs: `Textures13` on Omega, `Textures14` on Piers.

## What fails silently

- An RGBA source is cached at full size, so caching saves nothing and nothing
  says so.
- Lossless WebP silently takes the PNG path.
- WebP under a `.png` name works on Piers and fails on Omega.
- `folder.png` is ignored, with no fallback and no warning.
- A cache entry without its `sizes` row is never found.
- A cache key with upper-case percent-hex renders blank.

## Open questions

- Whether the 1080 cap is configurable, and whether it applies identically to
  every art type, has not been checked.
- Whether Piers' content sniffing is deliberate or incidental is unknown — it was
  observed, not traced to a code path, so it should not be relied on.

## See also

- [`kodi-library-data`](../kodi-library-data/SKILL.md) — the Textures database
  alongside Kodi's others
- [`kodi-performance`](../kodi-performance/SKILL.md) — why image size matters
  more on a TV box than on your desktop
