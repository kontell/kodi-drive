#!/usr/bin/env bash
# Scaffold a kodi-drive skill from the template.
#
# Usage: scripts/new-skill.sh <skill-name> [skills|addons|adjacent]
#
# Licence: GPL-2.0-or-later
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
name="${1:-}"
section="${2:-skills}"

if [ -z "$name" ]; then
  echo "usage: $(basename "$0") <skill-name> [skills|addons|adjacent]" >&2
  exit 2
fi

case "$section" in
  skills|addons|adjacent) ;;
  *) echo "error: section must be skills, addons, or adjacent (got '$section')" >&2
     exit 2 ;;
esac

if ! printf '%s' "$name" | grep -qE '^[a-z0-9][a-z0-9.-]*$'; then
  echo "error: '$name' must be lower-case kebab-case; add-on ids may contain dots" >&2
  exit 2
fi

dir="$repo/$section/$name"
if [ -e "$dir" ]; then
  echo "error: $section/$name already exists" >&2
  echo "Editing an existing skill is usually the better contribution — see CONTRIBUTING.md" >&2
  exit 1
fi

mkdir -p "$dir"
sed -e "s/SKILL_NAME/$name/" \
    -e "s/YYYY-MM-DD/$(date +%F)/" \
    "$repo/templates/SKILL.md.template" > "$dir/SKILL.md"

echo "created $section/$name/SKILL.md"
echo
echo "Before you write: what are the three closest existing skills, and why is this"
echo "not an edit to one of them? CONTRIBUTING.md asks for that in the PR."
echo
grep -ril "$name" "$repo/skills" "$repo/addons" "$repo/adjacent" 2>/dev/null \
  | grep -v "^$dir" | head -10 | sed 's/^/  possibly related: /' || true
echo
echo "Then: python3 scripts/validate.py && python3 scripts/scrub.py --detect"
