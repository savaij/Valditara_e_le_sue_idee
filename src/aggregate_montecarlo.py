#!/usr/bin/env python3
"""Aggrega su più seed i riepiloghi di simulate_realloc.py (approccio Monte Carlo).

simulate_realloc.py introduce due fonti di casualità a parità di dati e
parametri: il campionamento Binomiale(m_min, quota_campione) che seleziona
quali studenti del pool m_min entrano nello scenario, e - se si usa
--ordine-origine-casuale - l'ordine (permutato via seed) con cui le unità di
origine di ciascun gruppo competono per gli stessi posti nelle destinazioni,
che a parità di quota_campione (anche 1.00) può cambiare il flusso di
riallocazione risultante. Questo script legge i
riepiloghi JSON di più run con seed diversi (stessa quota_campione, stessi
altri parametri) e calcola media, deviazione standard, minimo e massimo delle
metriche principali, come stima Monte Carlo della loro incertezza.

Uso:
    python3 src/aggregate_montecarlo.py --quota-campione 0.20 --n-seeds 50 --seed-base 0
    python3 src/aggregate_montecarlo.py --quota-campione 1.00 --seeds 1 7 23 42
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
YEAR = "202425"

SCALAR_METRICS = [
    "studenti_campionati_totale",
    "studenti_riallocati_totale",
    "studenti_non_riallocati_totale",
    "quota_riallocati_su_campionati",
]

DISTANCE_METRICS = ["media_km", "mediana_km", "p90_km", "p95_km", "max_km", "min_km"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--quota-campione", type=float, required=True,
                         help="Quota campione della serie di run da aggregare (deve combaciare con i file esistenti).")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--seeds", type=int, nargs="+", help="Lista esplicita di seed da aggregare.")
    group.add_argument("--n-seeds", type=int, help="Numero di seed consecutivi da aggregare (con --seed-base).")
    parser.add_argument("--seed-base", type=int, default=0, help="Primo seed se si usa --n-seeds (default 0).")
    parser.add_argument("--ordine-origine-casuale", action="store_true",
                         help="Aggrega i run generati con --ordine-origine-casuale su simulate_realloc.py "
                              "(deve combaciare con come sono stati generati i file).")
    return parser.parse_args()


def stats(values: list[float]) -> dict[str, object]:
    n = len(values)
    if n == 0:
        return {"n_run": 0}
    mean = statistics.fmean(values)
    return {
        "n_run": n,
        "media": round(mean, 4),
        "dev_std": round(statistics.stdev(values), 4) if n > 1 else 0.0,
        "min": round(min(values), 4),
        "max": round(max(values), 4),
    }


def main() -> None:
    args = parse_args()
    if args.seeds is not None:
        seeds = args.seeds
    else:
        seeds = list(range(args.seed_base, args.seed_base + args.n_seeds))

    suffix_q = f"q{int(round(args.quota_campione * 100)):03d}"
    suffix_ordine = "_ordcas" if args.ordine_origine_casuale else ""
    summaries = []
    missing = []
    for seed in seeds:
        path = RESULTS / f"simulazione_riepilogo_{YEAR}_{suffix_q}_seed{seed}{suffix_ordine}.json"
        if not path.exists():
            missing.append(seed)
            continue
        summaries.append(json.loads(path.read_text(encoding="utf-8")))

    if missing:
        print(f"ATTENZIONE: mancano i riepiloghi per {len(missing)} seed: {missing}")
    if not summaries:
        raise SystemExit("Nessun riepilogo trovato: eseguire prima simulate_realloc.py per questi seed.")

    result: dict[str, object] = {
        "school_year": summaries[0]["school_year"],
        "quota_campione": args.quota_campione,
        "n_seed_richiesti": len(seeds),
        "n_seed_trovati": len(summaries),
        "seed_mancanti": missing,
        "nota": (
            "Stima Monte Carlo: media e deviazione standard delle metriche calcolate su run "
            "indipendenti con seed diversi, a parita' di quota_campione e degli altri parametri. "
            "Il campionamento Binomiale(m_min, quota_campione) e la sua interazione con la "
            "capacita' delle destinazioni sono l'unica fonte di variabilita' tra i run."
        ),
    }

    for metric in SCALAR_METRICS:
        values = [s[metric] for s in summaries if s.get(metric) is not None]
        result[metric] = stats(values)

    distanza_agg: dict[str, object] = {}
    for metric in DISTANCE_METRICS:
        values = [
            s["distanza_km"][metric]
            for s in summaries
            if s.get("distanza_km", {}).get("n", 0) > 0
        ]
        distanza_agg[metric] = stats(values)
    result["distanza_km"] = distanza_agg

    ordini = sorted({k for s in summaries for k in s.get("distanza_km_per_ordine_scuola", {})})
    per_ordine: dict[str, object] = {}
    for ordine in ordini:
        values = [
            s["distanza_km_per_ordine_scuola"][ordine]["media_km"]
            for s in summaries
            if s.get("distanza_km_per_ordine_scuola", {}).get(ordine, {}).get("n", 0) > 0
        ]
        per_ordine[ordine] = stats(values)
    result["distanza_media_km_per_ordine_scuola"] = per_ordine

    out_path = RESULTS / f"simulazione_montecarlo_{YEAR}_{suffix_q}_n{len(summaries)}{suffix_ordine}.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\nScritto: {out_path}")


if __name__ == "__main__":
    main()
