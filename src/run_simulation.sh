#!/usr/bin/env bash
set -euo pipefail

# Esegue la simulazione realistica degli spostamenti per il criterio del 30%.
# Richiede che analyze.py abbia già prodotto data_processed/unita_202425.csv.
# Ogni unità sopra soglia rialloca esattamente m_min (nessun campionamento).
# Entrambe le modalità usano 5 km in linea d'aria, capienza 30 per classe e
# non vincolano la tipologia anagrafica (parametri dello scenario consegnato).
#
# Due modalità d'uso:
#
#   1) singola run con un seed fisso (comportamento originale):
#        bash src/run_simulation.sh [seed]
#
#   2) Monte Carlo: N run indipendenti con seed diversi, seguite dal calcolo
#      di media/deviazione standard delle metriche principali. Produce un
#      unico JSON di dettaglio con le metriche di ogni run e un unico JSON
#      riepilogativo. Ogni run usa anche --ordine-origine-casuale: il flusso
#      di riallocazione dipende dall'ordine con cui le unità di origine
#      competono per le stesse destinazioni, quindi è quella l'unica fonte di
#      variabilità simulata tra run (a parità di m_min per unità).
#        bash src/run_simulation.sh --montecarlo N_SEED [SEED_BASE]
#      Esempio: 50 run con seed 0..49:
#        bash src/run_simulation.sh --montecarlo 50

project_root="$(cd "$(dirname "$0")/.." && pwd)"

if [[ "${1:-}" == "--montecarlo" ]]; then
    n_seeds="${2:?specificare il numero di seed, es: --montecarlo 50}"
    seed_base="${3:-0}"
    python3 "$project_root/src/aggregate_montecarlo.py" \
        --n-seeds "$n_seeds" --seed-base "$seed_base" --ordine-origine-casuale
else
    seed="${1:-42}"
    python3 "$project_root/src/simulate_realloc.py" --seed "$seed"
fi
