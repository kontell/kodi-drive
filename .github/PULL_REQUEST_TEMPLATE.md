# STOP — read this before filling anything in

**If you did not run this against a live Kodi, and cannot cite a source file or an official doc, do not
open this PR.** Open an [Unverified observation](../../issues/new?template=unverified-observation.yml)
issue instead.

That is not a rejection. An issue saying "I saw X but could not confirm it" is a genuinely useful
contribution and we want it. A skill saying "X happens" when you were not sure is not — every future agent
that reads it will trust it completely and has no way to check.

If you are still here, you have evidence. Paste it below.

---

## What this adds or changes

<!-- One or two sentences. What will a reader be able to do that they could not before? -->

## Evidence

**Fill these in. Do not tick them.** An empty block means the claim is not ready — which is exactly what
we want to be able to see.

Duplicate this section per claim if the PR makes more than one.

### Claim 1

> <!-- State the claim in one sentence, as it appears in the skill. -->

- **Tier:** `observed` / `sourced` / `inferred` <!-- delete the two that do not apply -->
- **Kodi version(s) tested:** <!-- e.g. 21.3 Omega, 22.0b1 Piers. Not "21+". -->
- **Platform(s):** <!-- e.g. Linux x86_64, Android TV -->

**Command run** *(observed)* or **source reference** *(sourced)* or **premises** *(inferred)*:

```
```

**Actual output:**

```
```

---

## Duplication check

**List the three existing skills closest to this one, and say why this is not an edit to one of them.**
If you cannot name three, you have not looked. Try `grep -ril "<key term>" skills/ addons/ adjacent/`.

1.
2.
3.

Why this is new rather than an edit:

## Checks

- [ ] `python3 scripts/validate.py` passes
- [ ] `python3 scripts/scrub.py --detect` passes
- [ ] No hostnames, IPs, tokens, serials, usernames, home paths, or library contents anywhere in the diff —
      including inside pasted log excerpts, which carry credentials at debug level
- [ ] `metadata.verified-*` lists only versions and platforms I actually tested,
      and `metadata.category` is set
- [ ] Anything I am unsure about is under an `## Open questions` heading, not stated as fact
- [ ] This is not about an add-on excluded by the [add-on policy](../CONTRIBUTING.md#add-on-policy)
      (infringing content, builds, wizards, DRM circumvention). Unofficial and scraper add-ons are fine.
