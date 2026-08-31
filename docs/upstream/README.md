# Upstream snapshots

Verbatim copies of documents owned by other projects, kept here **only so that
changes to them are detectable**. They are not the canonical copy and they are not
documentation in their own right.

**Do not hand-edit anything in this directory.** The files are byte-identical to
upstream, which is what lets `scripts/sync-upstream-docs.py` compare a single git
blob hash instead of a diff. An edit here reports as drift and gets overwritten by
the next `--update`.

Provenance for each file — the upstream URL, the blob hash and why it is tracked —
is in `manifest.json`.

## Why mirror at all

This repo's rule is to link rather than copy, because a paraphrase of someone
else's document goes stale silently and the reader has no way to tell. A verbatim
snapshot plus a hash is the exception that keeps the rule working: the pointer
stays canonical, and the moment upstream changes, CI says so.

The reason it matters for `AGENTS.md` in particular is that Kodi's team have said
it is a starting point they intend to expand. A skill that summarises its current
scope will be wrong at some point, and this is how we find out when.

## Updating

```sh
python3 scripts/sync-upstream-docs.py --check    # what CI runs weekly
python3 scripts/sync-upstream-docs.py --update   # refresh snapshot and manifest
```

After an `--update`, **re-read the skills that cite the document.** The snapshot
refreshing is the easy half; the point of the alert is that a skill's summary of
it may now be wrong. `grep -rl upstream/xbmc-AGENTS skills/` finds the citations.
