#!/usr/bin/env bash
set -euo pipefail

# Esegue analyze.py (se non già fatto) e poi la simulazione realistica degli
# spostamenti in due scenari:
#   - default: quota_campione=0.20 (proxy controfattuale), seed=42
#   - completo: quota_campione=1.00 (tutto il pool m_min), stesso seed, come
#     limite superiore di confronto con lo scenario di default.
#
# Uso: bash src/run_simulation.sh [seed]

project_root="$(cd "$(dirname "$0")/.." && pwd)"
seed="${1:-42}"

python3 "$project_root/src/simulate_realloc.py" --quota-campione 0.20 --seed "$seed"
python3 "$project_root/src/simulate_realloc.py" --quota-campione 1.00 --seed "$seed"
