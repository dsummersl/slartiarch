#!/usr/bin/env bash
# Render every Mermaid fixture with mermaid-cli, proving the subset slarti reads is
# valid Mermaid (ADR-0004). Node is needed here, in slarti's own CI, and nowhere else.
set -euo pipefail

out="$(mktemp -d)"
trap 'rm -rf "$out"' EXIT

status=0
while IFS= read -r -d '' fixture; do
  name="$(basename "$fixture")"
  case "$fixture" in
    *.md) target="$out/$name" ;;
    *) target="$out/$name.svg" ;;
  esac
  if npx --no-install mmdc --quiet -p .github/puppeteer.json -i "$fixture" -o "$target" \
      >"$out/log" 2>&1; then
    echo "rendered $fixture"
  else
    echo "FAILED   $fixture" >&2
    cat "$out/log" >&2
    status=1
  fi
done < <(find tests/data/mermaid docs/mermaid.md docs/architecture.md README.md -type f \
           \( -name '*.mmd' -o -name '*.md' \) -print0 | sort -z)

exit "$status"
