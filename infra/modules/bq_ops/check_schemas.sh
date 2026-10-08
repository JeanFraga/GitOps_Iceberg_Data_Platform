#!/usr/bin/env bash
# Diff each declared schema file against the live BigQuery table (name, type, mode).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/../../.." && pwd)"
project="$(sed -n 's/^project_id: *//p' "$root/config/resolved.yaml")"
# bq reports legacy type names; map standard aliases so both sides compare equal.
norm='[.[]|{name,type:({"INT64":"INTEGER","FLOAT64":"FLOAT","BOOL":"BOOLEAN"}[.type]//.type),mode:(.mode//"NULLABLE")}]'
rc=0
for f in "$here"/schemas/*.json; do
  t="$(basename "$f" .json)"
  if diff <(jq -S "$norm" "$f") <(bq show --schema --format=prettyjson "$project:$t" | jq -S "$norm"); then
    echo "OK   $t"
  else
    echo "DIFF $t"; rc=1
  fi
done
exit $rc
