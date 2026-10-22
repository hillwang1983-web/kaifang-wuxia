#!/bin/sh
set -eu
PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
export PATH
cd "$(dirname "$0")"
exec node scripts/update-preview.mjs "$@"
