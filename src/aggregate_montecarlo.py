#!/usr/bin/env python3
"""Esegue e aggrega le simulazioni Monte Carlo per entrambe le quote."""

from __future__ import annotations

import argparse
import json
import statistics
from datetime import date
from pathlib import Path

import simulate_realloc


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
YEAR = "202425"
QUOTAS = (0.20, 1.00)

SCALAR_METRICS = [
    "studenti_m_min_pool_totale",
    "studenti_campionati_totale",
    "studenti_riallocati_totale",
    "studenti_non_riallocati_totale",
    "quota_riallocati_su_campionati",
]
DISTANCE_METRICS = ["media_km", "mediana_km", "p90_km", "p95_km", "max_km", "min_km"]
QUALITY_METRICS = [
    "violazioni_soglia_30_in_destinazioni",
    "violazioni_capacita_in_destinazioni",
    "violazioni_tipologia_scuola_in_destinazioni",
    "unita_origine_con_bilancio_incoerente",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Esegue N run per seed e per quota; salva un dettaglio e un riepilogo complessivi."
    )
    parser.add_argument("--n-seeds", type=int, required=True, help="Numero di seed consecutivi per quota.")
    parser.add_argument("--seed-base", type=int, default=0, help="Primo seed (default 0).")
    parser.add_argument(
        "--ordine-origine-casuale",
        action="store_true",
        help="Randomizza l'ordine delle unità di origine in ogni run.",
    )
    return parser.parse_args()


def stats(values: list[float]) -> dict[str, object]:
    if not values:
        return {"n_run": 0}
    return {
        "n_run": len(values),
        "media": round(statistics.fmean(values), 4),
        "dev_std": round(statistics.stdev(values), 4) if len(values) > 1 else 0.0,
        "min": round(min(values), 4),
        "max": round(max(values), 4),
    }


def aggregate_distance_groups(
    runs: list[dict[str, object]], field: str
) -> dict[str, dict[str, dict[str, object]]]:
    groups = sorted(
        {
            group
            for run in runs
            for group in run.get(field, {})  # type: ignore[union-attr]
        }
    )
    result: dict[str, dict[str, dict[str, object]]] = {}
    for group in groups:
        group_stats: dict[str, dict[str, object]] = {}
        for metric in DISTANCE_METRICS:
            values = [
                float(distances[metric])
                for run in runs
                if (distances := run.get(field, {}).get(group, {})).get("n", 0) > 0  # type: ignore[union-attr]
                and distances.get(metric) is not None
            ]
            group_stats[metric] = stats(values)
        result[group] = group_stats
    return result


def aggregate_quota(runs: list[dict[str, object]], quota: float) -> dict[str, object]:
    result: dict[str, object] = {
        "quota_campione": quota,
        "n_run": len(runs),
    }
    for metric in SCALAR_METRICS:
        result[metric] = stats([float(run[metric]) for run in runs if run.get(metric) is not None])

    result["distanza_km"] = {
        metric: stats(
            [
                float(run["distanza_km"][metric])
                for run in runs
                if run.get("distanza_km", {}).get("n", 0) > 0  # type: ignore[union-attr]
                and run["distanza_km"].get(metric) is not None  # type: ignore[union-attr]
            ]
        )
        for metric in DISTANCE_METRICS
    }
    result["distanza_km_per_ordine_scuola"] = aggregate_distance_groups(
        runs, "distanza_km_per_ordine_scuola"
    )
    result["distanza_km_per_regione"] = aggregate_distance_groups(runs, "distanza_km_per_regione")
    result["controlli_qualita"] = {
        metric: stats(
            [float(run["controlli_qualita"][metric]) for run in runs]
        )
        for metric in QUALITY_METRICS
    }
    return result


def main() -> None:
    args = parse_args()
    if args.n_seeds <= 0:
        raise SystemExit("--n-seeds deve essere maggiore di zero")

    seeds = range(args.seed_base, args.seed_base + args.n_seeds)
    runs_by_quota: dict[float, list[dict[str, object]]] = {quota: [] for quota in QUOTAS}

    for quota in QUOTAS:
        print(f"Monte Carlo quota {quota:.2f}: {args.n_seeds} run", flush=True)
        for index, seed in enumerate(seeds, start=1):
            sim_args = argparse.Namespace(
                quota_campione=quota,
                seed=seed,
                capienza_percentile=95.0,
                consenti_cambio_gestione=False,
                consenti_cambio_tipologia_scuola=False,
                ordine_origine_casuale=args.ordine_origine_casuale,
                max_km=None,
            )
            runs_by_quota[quota].append(
                simulate_realloc.run_simulation(sim_args, write_outputs=False, print_summary=False)
            )
            if index % 50 == 0 or index == args.n_seeds:
                print(f"  completati {index}/{args.n_seeds}", flush=True)

    suffix_order = "_ordcas" if args.ordine_origine_casuale else ""
    last_seed = args.seed_base + args.n_seeds - 1
    seed_range = f"seed{args.seed_base}-{last_seed}"
    common = f"{YEAR}_n{args.n_seeds}_{seed_range}{suffix_order}"

    detail = {
        "generated_on": date.today().isoformat(),
        "school_year": "2024/25",
        "n_seed_per_quota": args.n_seeds,
        "seed_base": args.seed_base,
        "seed_finale": last_seed,
        "ordine_origine_casuale": args.ordine_origine_casuale,
        "max_limit_per_class": simulate_realloc.MAX_LIMIT_PER_CLASS,
        "runs": [run for quota in QUOTAS for run in runs_by_quota[quota]],
    }
    summary = {
        "generated_on": date.today().isoformat(),
        "school_year": "2024/25",
        "n_seed_per_quota": args.n_seeds,
        "seed_base": args.seed_base,
        "seed_finale": last_seed,
        "ordine_origine_casuale": args.ordine_origine_casuale,
        "max_limit_per_class": simulate_realloc.MAX_LIMIT_PER_CLASS,
        "nota": (
            "Media, deviazione standard campionaria, minimo e massimo delle metriche per seed. "
            "La variabilità include il campionamento Binomiale(m_min, quota_campione) e, "
            "se attivo, l'ordine casuale delle unità di origine."
        ),
        "scenari": {
            f"q{int(round(quota * 100)):03d}": aggregate_quota(runs_by_quota[quota], quota)
            for quota in QUOTAS
        },
    }

    RESULTS.mkdir(parents=True, exist_ok=True)
    detail_path = RESULTS / f"simulazione_montecarlo_dettaglio_{common}.json"
    summary_path = RESULTS / f"simulazione_montecarlo_{common}.json"
    detail_path.write_text(json.dumps(detail, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nDettaglio scritto: {detail_path}")
    print(f"Riepilogo scritto: {summary_path}")


if __name__ == "__main__":
    main()
