#!/usr/bin/env python3
"""Ricostruisce i run Monte Carlo estremi e salva gli spostamenti oltre soglia."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

import simulate_realloc


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "results/simulazione_montecarlo_dettaglio_202425_n100_seed0-99_ordcas.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Seleziona i run con i massimi più alti, li riesegue e salva in CSV "
            "le coppie origine-destinazione oltre la soglia richiesta."
        )
    )
    parser.add_argument(
        "montecarlo_json",
        nargs="?",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"JSON di dettaglio Monte Carlo (default: {DEFAULT_INPUT})",
    )
    parser.add_argument(
        "--soglia-km",
        type=float,
        default=500.0,
        help="Distanza minima inclusiva da includere nel CSV (default: 500 km).",
    )
    parser.add_argument(
        "--top-runs",
        type=int,
        default=10,
        help="Quanti run con massimo sopra soglia rieseguire; 0 significa tutti (default: 10).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="CSV di destinazione (default: accanto al JSON di input).",
    )
    args = parser.parse_args()
    if args.soglia_km < 0:
        parser.error("--soglia-km deve essere maggiore o uguale a zero")
    if args.top_runs < 0:
        parser.error("--top-runs deve essere maggiore o uguale a zero")
    return args


def read_coordinates() -> dict[str, tuple[str, str]]:
    coordinates: dict[str, tuple[str, str]] = {}
    for row in simulate_realloc.read_csv(simulate_realloc.GEOCODING_PATH):
        code = row.get("codice_scuola", "").strip()
        if code:
            coordinates[code] = (row.get("lat", ""), row.get("lon", ""))
    return coordinates


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def replay_args(run: dict[str, object]) -> argparse.Namespace:
    applied_max_km = run.get("max_km_applicato")
    if applied_max_km in (None, "nessuno"):
        applied_max_km = None
    else:
        applied_max_km = float(applied_max_km)
    capienza = run.get("capienza_percentile")
    return argparse.Namespace(
        seed=int(run["seed"]),
        capienza_percentile=float(capienza) if capienza is not None else 95.0,
        consenti_cambio_gestione=bool(run.get("consenti_cambio_gestione", False)),
        consenti_cambio_tipologia_scuola=bool(run.get("consenti_cambio_tipologia_scuola", False)),
        ordine_origine_casuale=bool(run.get("ordine_origine_casuale", False)),
        max_km=applied_max_km,
    )


def main() -> None:
    args = parse_args()
    input_path = args.montecarlo_json
    if not input_path.is_file():
        raise SystemExit(f"File Monte Carlo non trovato: {input_path}")

    document = json.loads(input_path.read_text(encoding="utf-8"))
    runs = document.get("runs") if isinstance(document, dict) else None
    if not isinstance(runs, list):
        raise SystemExit("Il JSON deve contenere la lista 'runs' del dettaglio Monte Carlo.")

    candidates: list[tuple[float, dict[str, object]]] = []
    for run in runs:
        try:
            maximum = float(run["distanza_km"]["max_km"])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(maximum) and maximum >= args.soglia_km:
            candidates.append((maximum, run))
    candidates.sort(key=lambda item: item[0], reverse=True)
    if args.top_runs:
        candidates = candidates[: args.top_runs]

    output_path = args.output or input_path.with_name(
        f"{input_path.stem}_casi_sopra_{args.soglia_km:g}km.csv"
    )
    coordinates = read_coordinates()
    output_rows: list[dict[str, object]] = []
    original_max_limit = simulate_realloc.MAX_LIMIT_PER_CLASS

    try:
        for run_max, run in candidates:
            run_args = replay_args(run)
            configured_limit = run.get("max_limit_per_class")
            simulate_realloc.MAX_LIMIT_PER_CLASS = (
                int(configured_limit) if configured_limit is not None else None
            )

            detail_rows: list[dict[str, object]] = []
            summary = simulate_realloc.run_simulation(
                run_args,
                write_outputs=False,
                print_summary=False,
                detail_rows_out=detail_rows,
            )
            replayed_max = summary.get("distanza_km", {}).get("max_km")
            if replayed_max is not None and round(float(replayed_max), 3) != round(run_max, 3):
                print(
                    "ATTENZIONE: il massimo ricostruito non coincide con il JSON "
                    f"per seed={run_args.seed}: "
                    f"{replayed_max} km contro {run_max} km.",
                    file=sys.stderr,
                )

            for row in detail_rows:
                distance = float(row["distanza_km"])
                if distance < args.soglia_km:
                    continue
                origin_coords = coordinates.get(str(row["codice_scuola_origine"]), ("", ""))
                destination_coords = coordinates.get(
                    str(row["codice_scuola_destinazione"]), ("", "")
                )
                output_rows.append(
                    {
                        **row,
                        "max_km_json_run": run_max,
                        "max_km_ricostruito_run": replayed_max if replayed_max is not None else "",
                        "latitudine_origine": origin_coords[0],
                        "longitudine_origine": origin_coords[1],
                        "latitudine_destinazione": destination_coords[0],
                        "longitudine_destinazione": destination_coords[1],
                    }
                )
            print(
                f"Run seed={run_args.seed}: "
                f"max {run_max:g} km, ricostruito {replayed_max if replayed_max is not None else 'n/d'} km.",
                flush=True,
            )
    finally:
        simulate_realloc.MAX_LIMIT_PER_CLASS = original_max_limit

    output_rows.sort(key=lambda row: float(row["distanza_km"]), reverse=True)
    fields = [
        *simulate_realloc.DETAIL_FIELDS,
        "max_km_json_run",
        "max_km_ricostruito_run",
        "latitudine_origine",
        "longitudine_origine",
        "latitudine_destinazione",
        "longitudine_destinazione",
    ]
    write_csv(output_path, output_rows, fields)
    n_students = sum(int(row["n_studenti_spostati"]) for row in output_rows)
    print(
        f"\nRun selezionati: {len(candidates)} su {len(runs)}; "
        f"spostamenti oltre soglia: {len(output_rows)} "
        f"({n_students} studenti negli abbinamenti); CSV: {output_path}"
    )


if __name__ == "__main__":
    main()
