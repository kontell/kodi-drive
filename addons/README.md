# Add-on-specific skills

Knowledge that only makes sense inside one add-on or skin lives here, as
`addons/<addon-id>/SKILL.md`. Everything else — anything true of Kodi generally,
or of a whole class of add-ons — belongs in [`skills/`](../skills/).

## Where the line falls

The test is whether someone working on a *different* add-on would benefit.

| Belongs in `skills/` | Belongs here |
|---|---|
| Kodi caches add-on strings for the process lifetime | which of *this* add-on's strings are affected |
| A directory route must close its handle | this add-on's route table |
| Binary settings have no action-button callback | this add-on's login flow |
| The texture cache re-encodes only alpha-free sources | this add-on's artwork endpoints |

When in doubt, put it in `skills/`. A general skill that turns out to be
add-on-specific is a small mistake; add-on-specific knowledge hidden in a project
repo is the problem this repository exists to solve.

## Same rules apply

Add-on skills use the same frontmatter, the same
[verification bar](../CONTRIBUTING.md), and the same privacy rules as everything
else. A `metadata.verified` block naming the **add-on version** as well as the
Kodi version matters more here, because add-on internals move faster than Kodi's.

## Nothing here yet

The generic layer was built first, deliberately: most of what looked
add-on-specific in the source material turned out to be general once the
project-specific naming was stripped out.
