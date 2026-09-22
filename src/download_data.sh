#!/usr/bin/env bash
set -euo pipefail

# Download dei file MIM usati dal progetto. Il catalogo MIM espone i file
# nella directory .../catalogo/elements1/; i nomi contengono anno e data.

project_root="$(cd "$(dirname "$0")/.." && pwd)"
raw_dir="$project_root/data_raw"
base_url="https://dati.istruzione.it/opendata/opendata/catalogo/elements1"

mkdir -p "$raw_dir"

files=(
  ALUITASTRACITSTA20242520250831.csv
  ALUCORSOINDCLASTA20242520250831.csv
  SCUANAGRAFESTAT20242520250831.csv
  ALUITASTRACITPAR20242520250831.csv
  ALUCORSOINDCLAPAR20242520250831.csv
  SCUANAGRAFEPAR20242520250831.csv
  SCUANAAUTSTAT20242520250831.csv
  SCUANAAUTPAR20242520250831.csv
  SCUANAGRAFESTAT20262720260901.csv
  SCUANAGRAFEPAR20262720260901.csv
)

for file_name in "${files[@]}"; do
  curl --fail --location --retry 3 --user-agent 'Mozilla/5.0' \
    "$base_url/$file_name" -o "$raw_dir/$file_name"
done

echo "File MIM scaricati in $raw_dir"
