#!/usr/bin/env python3
"""Analisi riproducibile del criterio del 30% - MIM a.s. 2024/25.

Dipendenze: sola libreria standard Python 3.10+.

La base statistica dell'analisi è il flusso MIM per cittadinanza. Il flusso
classi/studenti viene usato come controllo indipendente del totale studenti e
per allegare il numero di classi quando la chiave corso è confrontabile. Le
anagrafiche sono unite per CodiceScuola (plesso).
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data_raw"
PROCESSED = ROOT / "data_processed"
RESULTS = ROOT / "results"
METADATA = ROOT / "metadata"
YEAR = "202425"
YEAR_LABEL = "2024/25"
THRESHOLD_NUM = 3
THRESHOLD_DEN = 10


UNIT_FIELDS = [
    "anno_scolastico",
    "tipo_gestione",
    "codice_scuola",
    "denominazione_scuola",
    "codice_istituto_riferimento",
    "denominazione_istituto_riferimento",
    "ordine_scuola",
    "anno_corso",
    "area_geografica",
    "regione",
    "provincia",
    "codice_comune",
    "comune",
    "indirizzo_scuola",
    "cap_scuola",
    "tipo_scuola_anagrafe",
    "fonte_anagrafe",
    "anagrafe_mappata",
    "alunni_italiani",
    "alunni_non_italiani",
    "alunni_totali",
    "quota_non_italiani",
    "sopra_30",
    "m_min",
    "classi_esatte",
    "alunni_classi_esatte",
    "delta_n_cittadinanza_meno_classi",
    "chiave_classi_confrontabile",
]


AGG_FIELDS = [
    "anno_scolastico",
    "livello_aggregazione",
    "tipo_gestione",
    "regione",
    "provincia",
    "codice_comune",
    "comune",
    "codice_scuola",
    "denominazione_scuola",
    "unita_totali",
    "unita_sopra_30",
    "studenti_totali_sopra_30",
    "studenti_non_italiani_sopra_30",
    "m_min_sopra_30",
    "m_min_pct_non_italiani_sopra_30",
    "m_min_pct_studenti_sopra_30",
    "studenti_totali_analizzati",
    "studenti_non_italiani_analizzati",
    "m_min_pct_non_italiani_analizzati",
    "m_min_pct_studenti_analizzati",
    "classi_esatte_sommate",
    "unita_con_chiave_classi_esatta",
    "unita_senza_chiave_classi_esatta",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    """Read a MIM CSV, preserving identifiers as strings."""

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: Iterable[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def as_int(value: str | int | None) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    return int(text) if text else None


def as_text(value: str | None) -> str:
    return (value or "").strip()


def pct(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return ""
    return f"{numerator / denominator:.6f}"


def ratio_float(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def ceil_excess(f: int, n: int) -> int:
    """Exact integer implementation of max(0, ceil(F - 0.30*N))."""

    excess_tenths = THRESHOLD_DEN * f - THRESHOLD_NUM * n
    if excess_tenths <= 0:
        return 0
    return (excess_tenths + THRESHOLD_DEN - 1) // THRESHOLD_DEN


def source_path(dataset: str, management: str) -> Path:
    suffix = "STA" if management == "statale" else "PAR"
    return RAW / f"{dataset}{suffix}{YEAR}20250831.csv"


def load_registry(management: str) -> tuple[dict[str, dict[str, str]], dict[str, int]]:
    """Load standard and autonomous-province school registries by plesso code."""

    suffix = "STAT" if management == "statale" else "PAR"
    standard_path = RAW / f"SCUANAGRAFE{suffix}{YEAR}20250831.csv"
    autonomous_path = RAW / f"SCUANAAUT{suffix}{YEAR}20250831.csv"

    registry: dict[str, dict[str, str]] = {}
    diagnostics = {
        "standard_rows": 0,
        "autonomous_rows": 0,
        "duplicate_codes": 0,
    }

    common_fields = {
        "area_geografica": "AREAGEOGRAFICA",
        "regione": "REGIONE",
        "provincia": "PROVINCIA",
        "codice_scuola": "CODICESCUOLA",
        "denominazione_scuola": "DENOMINAZIONESCUOLA",
        "indirizzo_scuola": "INDIRIZZOSCUOLA",
        "cap_scuola": "CAPSCUOLA",
        "codice_comune": "CODICECOMUNESCUOLA",
        "comune": "DESCRIZIONECOMUNE",
        "tipo_scuola_anagrafe": "DESCRIZIONETIPOLOGIAGRADOISTRUZIONESCUOLA",
    }

    def add(path: Path, source: str, include_reference: bool) -> None:
        rows = read_csv(path)
        if source == "standard":
            diagnostics["standard_rows"] = len(rows)
        else:
            diagnostics["autonomous_rows"] = len(rows)
        for raw in rows:
            code = as_text(raw.get("CODICESCUOLA"))
            if not code:
                continue
            if code in registry:
                diagnostics["duplicate_codes"] += 1
                continue
            item = {
                "fonte_anagrafe": source,
                "anagrafe_mappata": "1",
                "codice_istituto_riferimento": as_text(raw.get("CODICEISTITUTORIFERIMENTO"))
                if include_reference
                else "",
                "denominazione_istituto_riferimento": as_text(
                    raw.get("DENOMINAZIONEISTITUTORIFERIMENTO")
                )
                if include_reference
                else "",
            }
            for target, field in common_fields.items():
                item[target] = as_text(raw.get(field))
            registry[code] = item

    add(standard_path, "standard", management == "statale")
    add(autonomous_path, "autonome", management == "statale")
    return registry, diagnostics


def load_class_index(management: str) -> tuple[dict[tuple[str, str, str], dict[str, int]], dict[str, int]]:
    """Index classi/studenti on the exact course key; course 7 is not exact."""

    path = source_path("ALUCORSOINDCLA", management)
    rows = read_csv(path)
    index: dict[tuple[str, str, str], dict[str, int]] = {}
    diagnostics = {
        "rows": len(rows),
        "rows_course_7": 0,
        "students_total": 0,
        "classes_total": 0,
        "duplicate_keys": 0,
    }
    for raw in rows:
        code = as_text(raw.get("CODICESCUOLA"))
        order = as_text(raw.get("ORDINESCUOLA"))
        course = as_text(raw.get("ANNOCORSOCLASSE"))
        classes = as_int(raw.get("CLASSI")) or 0
        male = as_int(raw.get("ALUNNIMASCHI")) or 0
        female = as_int(raw.get("ALUNNIFEMMINE")) or 0
        students = male + female
        diagnostics["students_total"] += students
        diagnostics["classes_total"] += classes
        if course == "7":
            diagnostics["rows_course_7"] += 1
            continue
        key = (code, order, course)
        if key in index:
            diagnostics["duplicate_keys"] += 1
            continue
        index[key] = {"classi": classes, "alunni_classi": students}
    return index, diagnostics


def load_units(management: str) -> tuple[list[dict[str, object]], dict[str, object]]:
    registry, registry_diag = load_registry(management)
    class_index, class_diag = load_class_index(management)
    cit_path = source_path("ALUITASTRACIT", management)
    raw_units = read_csv(cit_path)

    diagnostics: dict[str, object] = {
        "management": management,
        "citizenship_rows": len(raw_units),
        "citizenship_duplicate_keys": 0,
        "citizenship_n_total": 0,
        "citizenship_f_total": 0,
        "citizenship_italiani_total": 0,
        "above_30_units": 0,
        "above_30_n_total": 0,
        "above_30_f_total": 0,
        "above_30_m_min_total": 0,
        "registry_missing_units": 0,
        "class_exact_matches": 0,
        "class_missing_exact": 0,
        "class_delta_nonzero": 0,
        "class_delta_sum": 0,
        "class_rows": class_diag["rows"],
        "class_course_7_rows": class_diag["rows_course_7"],
        "classes_students_total": class_diag["students_total"],
        "classes_total": class_diag["classes_total"],
        "registry_standard_rows": registry_diag["standard_rows"],
        "registry_autonomous_rows": registry_diag["autonomous_rows"],
        "registry_duplicate_codes": registry_diag["duplicate_codes"],
    }

    seen_keys: set[tuple[str, str, str]] = set()
    units: list[dict[str, object]] = []
    for raw in raw_units:
        code = as_text(raw.get("CODICESCUOLA"))
        order = as_text(raw.get("ORDINESCUOLA"))
        course = as_text(raw.get("ANNOCORSO"))
        key = (code, order, course)
        if key in seen_keys:
            diagnostics["citizenship_duplicate_keys"] += 1
        seen_keys.add(key)

        n = as_int(raw.get("ALUNNI")) or 0
        italiani = as_int(raw.get("ALUNNICITTADINANZAITALIANA")) or 0
        non_italiani = as_int(raw.get("ALUNNICITTADINANZANONITALIANA")) or 0
        if n != italiani + non_italiani:
            raise ValueError(
                f"ALUNNI != italiani + non italiani in {management} {key}: "
                f"{n} != {italiani} + {non_italiani}"
            )
        if n <= 0:
            raise ValueError(f"ALUNNI non positivo in {management} {key}: {n}")

        registry_row = registry.get(code)
        if registry_row is None:
            diagnostics["registry_missing_units"] += 1
            registry_row = {
                "fonte_anagrafe": "mancante",
                "anagrafe_mappata": "0",
                "codice_istituto_riferimento": "",
                "denominazione_istituto_riferimento": "",
                "area_geografica": "NON DISPONIBILE",
                "regione": "NON DISPONIBILE",
                "provincia": "NON DISPONIBILE",
                "codice_scuola": code,
                "denominazione_scuola": "NON DISPONIBILE",
                "indirizzo_scuola": "",
                "cap_scuola": "",
                "codice_comune": "NON DISPONIBILE",
                "comune": "NON DISPONIBILE",
                "tipo_scuola_anagrafe": "",
            }

        class_row = class_index.get(key)
        class_exact = class_row is not None
        classi_esatte = class_row["classi"] if class_row else ""
        alunni_classi = class_row["alunni_classi"] if class_row else ""
        delta = n - alunni_classi if class_exact else ""
        if class_exact:
            diagnostics["class_exact_matches"] += 1
            diagnostics["class_delta_sum"] += delta
            if delta != 0:
                diagnostics["class_delta_nonzero"] += 1
        else:
            diagnostics["class_missing_exact"] += 1

        above = THRESHOLD_DEN * non_italiani > THRESHOLD_NUM * n
        m_min = ceil_excess(non_italiani, n)
        diagnostics["citizenship_n_total"] += n
        diagnostics["citizenship_f_total"] += non_italiani
        diagnostics["citizenship_italiani_total"] += italiani
        if above:
            diagnostics["above_30_units"] += 1
            diagnostics["above_30_n_total"] += n
            diagnostics["above_30_f_total"] += non_italiani
            diagnostics["above_30_m_min_total"] += m_min

        units.append(
            {
                "anno_scolastico": YEAR,
                "tipo_gestione": management,
                "codice_scuola": code,
                "denominazione_scuola": registry_row["denominazione_scuola"],
                "codice_istituto_riferimento": registry_row["codice_istituto_riferimento"],
                "denominazione_istituto_riferimento": registry_row[
                    "denominazione_istituto_riferimento"
                ],
                "ordine_scuola": order,
                "anno_corso": course,
                "area_geografica": registry_row["area_geografica"],
                "regione": registry_row["regione"],
                "provincia": registry_row["provincia"],
                "codice_comune": registry_row["codice_comune"],
                "comune": registry_row["comune"],
                "indirizzo_scuola": registry_row["indirizzo_scuola"],
                "cap_scuola": registry_row["cap_scuola"],
                "tipo_scuola_anagrafe": registry_row["tipo_scuola_anagrafe"],
                "fonte_anagrafe": registry_row["fonte_anagrafe"],
                "anagrafe_mappata": registry_row["anagrafe_mappata"],
                "alunni_italiani": italiani,
                "alunni_non_italiani": non_italiani,
                "alunni_totali": n,
                "quota_non_italiani": f"{non_italiani / n:.6f}",
                "sopra_30": 1 if above else 0,
                "m_min": m_min,
                "classi_esatte": classi_esatte,
                "alunni_classi_esatte": alunni_classi,
                "delta_n_cittadinanza_meno_classi": delta,
                "chiave_classi_confrontabile": 1 if class_exact else 0,
            }
        )
    return units, diagnostics


def group_key(row: dict[str, object], fields: list[str]) -> tuple[str, ...]:
    return tuple(str(row.get(field, "")) for field in fields)


def aggregate_rows(
    rows: list[dict[str, object]],
    level: str,
    group_fields: list[str],
    management_label: str,
) -> list[dict[str, object]]:
    grouped: defaultdict[tuple[str, ...], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[group_key(row, group_fields)].append(row)

    output: list[dict[str, object]] = []
    for key, members in grouped.items():
        labels = dict(zip(group_fields, key))
        flagged = [row for row in members if int(row["sopra_30"]) == 1]
        all_n = sum(int(row["alunni_totali"]) for row in members)
        all_f = sum(int(row["alunni_non_italiani"]) for row in members)
        above_n = sum(int(row["alunni_totali"]) for row in flagged)
        above_f = sum(int(row["alunni_non_italiani"]) for row in flagged)
        above_m = sum(int(row["m_min"]) for row in flagged)
        exact_class_units = sum(int(row["chiave_classi_confrontabile"]) for row in members)
        missing_class_units = len(members) - exact_class_units
        classes_sum = sum(
            int(row["classi_esatte"])
            for row in members
            if row["classi_esatte"] != ""
        )
        out: dict[str, object] = {
            "anno_scolastico": YEAR,
            "livello_aggregazione": level,
            "tipo_gestione": management_label,
            "regione": "",
            "provincia": "",
            "codice_comune": "",
            "comune": "",
            "codice_scuola": "",
            "denominazione_scuola": "",
            "unita_totali": len(members),
            "unita_sopra_30": len(flagged),
            "studenti_totali_sopra_30": above_n,
            "studenti_non_italiani_sopra_30": above_f,
            "m_min_sopra_30": above_m,
            "m_min_pct_non_italiani_sopra_30": pct(above_m, above_f),
            "m_min_pct_studenti_sopra_30": pct(above_m, above_n),
            "studenti_totali_analizzati": all_n,
            "studenti_non_italiani_analizzati": all_f,
            "m_min_pct_non_italiani_analizzati": pct(above_m, all_f),
            "m_min_pct_studenti_analizzati": pct(above_m, all_n),
            "classi_esatte_sommate": classes_sum,
            "unita_con_chiave_classi_esatta": exact_class_units,
            "unita_senza_chiave_classi_esatta": missing_class_units,
        }
        for field in group_fields:
            out[field] = labels[field]
        output.append(out)
    return output


def build_aggregates(units: list[dict[str, object]]) -> list[dict[str, object]]:
    definitions = [
        ("plesso", ["codice_scuola", "denominazione_scuola", "codice_comune", "comune", "provincia", "regione"]),
        ("comune", ["codice_comune", "comune", "provincia", "regione"]),
        ("provincia", ["provincia", "regione"]),
        ("regione", ["regione"]),
        ("nazionale", []),
    ]
    output: list[dict[str, object]] = []
    managements = [
        ("tutte", units),
        ("statale", [row for row in units if row["tipo_gestione"] == "statale"]),
        ("paritaria", [row for row in units if row["tipo_gestione"] == "paritaria"]),
    ]
    for management_label, subset in managements:
        for level, fields in definitions:
            output.extend(aggregate_rows(subset, level, fields, management_label))
    order = {"nazionale": 0, "regione": 1, "provincia": 2, "comune": 3, "plesso": 4}
    output.sort(
        key=lambda row: (
            row["tipo_gestione"],
            order[row["livello_aggregazione"]],
            str(row.get("regione", "")),
            str(row.get("provincia", "")),
            str(row.get("comune", "")),
            str(row.get("codice_scuola", "")),
        )
    )
    return output


def make_qc_row(metric: str, value: object, management: str, note: str = "") -> dict[str, object]:
    return {
        "anno_scolastico": YEAR,
        "metrica": metric,
        "tipo_gestione": management,
        "valore": value,
        "nota": note,
    }


def build_qc(diagnostics: list[dict[str, object]], units: list[dict[str, object]]) -> list[dict[str, object]]:
    qc: list[dict[str, object]] = []
    for diag in diagnostics:
        mgmt = str(diag["management"])
        qc.extend(
            [
                make_qc_row("righe_studenti_cittadinanza", diag["citizenship_rows"], mgmt),
                make_qc_row("studenti_totali_cittadinanza", diag["citizenship_n_total"], mgmt),
                make_qc_row("studenti_non_italiani_cittadinanza", diag["citizenship_f_total"], mgmt),
                make_qc_row("unità_sopra_30", diag["above_30_units"], mgmt),
                make_qc_row("studenti_in_unità_sopra_30", diag["above_30_n_total"], mgmt),
                make_qc_row("non_italiani_in_unità_sopra_30", diag["above_30_f_total"], mgmt),
                make_qc_row("m_min_in_unità_sopra_30", diag["above_30_m_min_total"], mgmt),
                make_qc_row("righe_dataset_classi_studenti", diag["class_rows"], mgmt),
                make_qc_row("studenti_totali_classi_studenti", diag["classes_students_total"], mgmt),
                make_qc_row("classi_totali", diag["classes_total"], mgmt),
                make_qc_row("righe_classi_con_anno_7_pluriclasse", diag["class_course_7_rows"], mgmt),
                make_qc_row("unità_con_chiave_classi_esatta", diag["class_exact_matches"], mgmt),
                make_qc_row("unità_senza_chiave_classi_esatta", diag["class_missing_exact"], mgmt),
                make_qc_row("unità_con_delta_N_nonzero", diag["class_delta_nonzero"], mgmt),
                make_qc_row("somma_delta_N_cittadinanza_meno_classi", diag["class_delta_sum"], mgmt),
                make_qc_row("unità_senza_anagrafica", diag["registry_missing_units"], mgmt),
                make_qc_row("righe_anagrafe_standard", diag["registry_standard_rows"], mgmt),
                make_qc_row("righe_anagrafe_autonome", diag["registry_autonomous_rows"], mgmt),
            ]
        )

    combined_n_cit = sum(int(row["alunni_totali"]) for row in units)
    combined_n_class = sum(
        int(row["alunni_classi_esatte"])
        for row in units
        if row["alunni_classi_esatte"] != ""
    )
    qc.append(
        make_qc_row(
            "studenti_totali_dataset_classi_tutte_le_righe",
            sum(int(d["classes_students_total"]) for d in diagnostics),
            "tutte",
            "Confronto con il totale del flusso cittadinanza; include anche l'anno classe 7.",
        )
    )
    qc.append(
        make_qc_row(
            "studenti_totali_dataset_cittadinanza",
            combined_n_cit,
            "tutte",
            "N base dell'analisi.",
        )
    )
    qc.append(
        make_qc_row(
            "studenti_totali_classi_solo_chiavi_esatte",
            combined_n_class,
            "tutte",
            "Non è un confronto completo perché l'anno classe 7 non è joinabile al corso.",
        )
    )
    return qc


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_hashes() -> None:
    rows = []
    for path in sorted(RAW.glob("*.csv")):
        rows.append({"file": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)})
    write_csv(METADATA / "sha256_raw.csv", rows, ["file", "bytes", "sha256"])


def main() -> None:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    METADATA.mkdir(parents=True, exist_ok=True)

    all_units: list[dict[str, object]] = []
    diagnostics: list[dict[str, object]] = []
    for management in ("statale", "paritaria"):
        units, diag = load_units(management)
        all_units.extend(units)
        diagnostics.append(diag)

    all_units.sort(
        key=lambda row: (
            str(row["tipo_gestione"]),
            str(row["regione"]),
            str(row["provincia"]),
            str(row["comune"]),
            str(row["codice_scuola"]),
            str(row["ordine_scuola"]),
            int(row["anno_corso"]),
        )
    )
    flagged = sorted(
        [row for row in all_units if int(row["sopra_30"]) == 1],
        key=lambda row: (-float(row["quota_non_italiani"]), -int(row["m_min"]), str(row["codice_scuola"])),
    )

    write_csv(PROCESSED / f"unita_{YEAR}.csv", all_units, UNIT_FIELDS)
    write_csv(PROCESSED / f"unita_sopra_30_{YEAR}.csv", flagged, UNIT_FIELDS)

    aggregates = build_aggregates(all_units)
    write_csv(RESULTS / f"aggregati_{YEAR}.csv", aggregates, AGG_FIELDS)
    national = [
        row
        for row in aggregates
        if row["livello_aggregazione"] == "nazionale" and row["tipo_gestione"] == "tutte"
    ]
    write_csv(RESULTS / f"aggregati_nazionale_{YEAR}.csv", national, AGG_FIELDS)

    qc = build_qc(diagnostics, all_units)
    write_csv(RESULTS / f"controlli_qualita_{YEAR}.csv", qc, ["anno_scolastico", "metrica", "tipo_gestione", "valore", "nota"])

    top = flagged[:100]
    write_csv(RESULTS / f"top_100_unita_sopra_30_{YEAR}.csv", top, UNIT_FIELDS)

    summary = {
        "generated_on": date.today().isoformat(),
        "school_year": YEAR_LABEL,
        "threshold": 0.30,
        "formula": "M_min = max(0, ceil(F - 0.30*N))",
        "unit_key": ["tipo_gestione", "CODICESCUOLA", "ORDINESCUOLA", "ANNOCORSO"],
        "units": len(all_units),
        "units_above_30": len(flagged),
        "students": sum(int(row["alunni_totali"]) for row in all_units),
        "non_italian_students": sum(int(row["alunni_non_italiani"]) for row in all_units),
        "students_in_units_above_30": sum(int(row["alunni_totali"]) for row in flagged),
        "non_italian_students_in_units_above_30": sum(int(row["alunni_non_italiani"]) for row in flagged),
        "m_min_in_units_above_30": sum(int(row["m_min"]) for row in flagged),
        "anagrafe_missing_units": sum(1 for row in all_units if row["anagrafe_mappata"] == "0"),
        "class_exact_key_missing_units": sum(1 for row in all_units if row["chiave_classi_confrontabile"] == 0),
        "managements": ["statale", "paritaria"],
    }
    (RESULTS / f"summary_{YEAR}.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    write_hashes()

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
