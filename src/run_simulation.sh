#!/usr/bin/env bash
set -euo pipefail

# Esegue analyze.py (se non già fatto) e poi la simulazione realistica degli
# spostamenti in due scenari:
#   - default: quota_campione=0.20 (proxy controfattuale)
#   - completo: quota_campione=1.00 (tutto il pool m_min), come limite
#     superiore di confronto con lo scenario di default.
#
# Due modalità d'uso:
#
#   1) singola run con un seed fisso (comportamento originale):
#        bash src/run_simulation.sh [seed]
#
#   2) Monte Carlo: N run indipendenti con seed diversi per ciascuno scenario,
#      seguite dal calcolo di media/deviazione standard delle metriche
#      principali (aggregate_montecarlo.py). Ogni run usa anche
#      --ordine-origine-casuale: a parità di quota_campione (anche 1.00) il
#      flusso di riallocazione dipende dall'ordine con cui le unità di
#      origine competono per le stesse destinazioni, quindi è quella la
#      principale fonte di variabilità simulata; il campionamento Binomiale
#      su quota_campione < 1.00 si aggiunge senza sostituirla.
#        bash src/run_simulation.sh --montecarlo N_SEED [SEED_BASE]
#      Esempio: 50 run con seed 0..49 per ogni scenario:
#        bash src/run_simulation.sh --montecarlo 50

project_root="$(cd "$(dirname "$0")/.." && pwd)"

if [[ "${1:-}" == "--montecarlo" ]]; then
    n_seeds="${2:?specificare il numero di seed, es: --montecarlo 50}"
    seed_base="${3:-0}"
    for quota in 0.20 1.00; do
        for ((i = 0; i < n_seeds; i++)); do
            seed=$((seed_base + i))
            python3 "$project_root/src/simulate_realloc.py" \
                --quota-campione "$quota" --seed "$seed" --ordine-origine-casuale
        done
        python3 "$project_root/src/aggregate_montecarlo.py" \
            --quota-campione "$quota" --n-seeds "$n_seeds" --seed-base "$seed_base" --ordine-origine-casuale
    done
else
    seed="${1:-42}"
    python3 "$project_root/src/simulate_realloc.py" --quota-campione 0.20 --seed "$seed"
    python3 "$project_root/src/simulate_realloc.py" --quota-campione 1.00 --seed "$seed"
fi
