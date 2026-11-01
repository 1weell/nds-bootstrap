#!/bin/sh
# Characterize the historical sliced evaluator against upstream rcheevos on the host.
set -eu
cd "$(dirname "$0")/.."
RC=retail/cardenginei/arm9_ra/rcheevos
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT
${CC:-cc} -std=gnu99 -O2 -I"$RC/include" -I"$RC/src" \
    tools/ra_slice_regression.c "$RC"/src/rcheevos/*.c \
    "$RC"/src/rc_util.c "$RC"/src/rc_compat.c "$RC"/src/rc_version.c \
    "$RC"/src/rhash/md5.c -lm -o "$out/ra_slice_regression"
"$out/ra_slice_regression"
