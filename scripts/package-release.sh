#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="${1:-5.4.9825-dev-personal}"
OUT="$ROOT/release-assets/binary-ninja-rekey-${VERSION}-source.zip"
cd "$ROOT"
rm -f "$OUT"
zip -qr "$OUT" README.md binary-ninja-5.4.9825-dev-personal
shasum -a 256 "$OUT" > "$OUT.sha256"
printf 'created %s\n' "$OUT"
