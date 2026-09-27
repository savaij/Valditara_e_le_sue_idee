#!/usr/bin/env python3
"""Simulazione realistica degli spostamenti per il criterio del 30% - MIM 2024/25.

Estende `analyze.py`: quello script calcola solo un limite inferiore aritmetico
(`m_min`, senza sostituzione) per ciascuna unità sopra soglia. Questo script
tenta di collocare concretamente quegli studenti in unità riceventi realmente
equivalenti, rispettandone capacità e soglia del 30%, e misura la distanza
geografica implicata.

Dipendenze: libreria standard + numpy (solo per questo script; `analyze.py`
resta stdlib-only). numpy è usato per RNG riproducibile e calcolo vettoriale
delle distanze.

## Definizione di "unità equivalente" (destinazione candidata)

Per uno studente da riallocare, spostato da un'unità
(tipo_gestione, codice_scuola, ordine_scuola, anno_corso), una destinazione è
considerata equivalente se e solo se:

- stesso `tipo_gestione` (statale <-> statale, paritaria <-> paritaria): un
  ricollocamento amministrativo tra scuola statale e paritaria non è
  realistico (iscrizione, retta, gestione differenti). Disattivabile con
  `--consenti-cambio-gestione` come verifica di sensitività, non di default.
- stesso `ordine_scuola` (primaria / secondaria I grado / secondaria II
  grado): non si sposta un alunno di ordine diverso.
- stesso `anno_corso` (stesso anno di corso, non genericamente lo stesso
  ordine): per continuità didattica un alunno di classe 3 non può essere
  inserito in una classe 4.
- stesso "cluster" di tipologia/indirizzo scolastico (es. liceo scientifico,
  istituto tecnico commerciale, alberghiero...), derivato dalla colonna
  anagrafica `DESCRIZIONETIPOLOGIAGRADOISTRUZIONESCUOLA` (campo
  `tipo_scuola_anagrafe` in `unita_202425.csv`) tramite la tabella
  `SCHOOL_TYPE_CLUSTERS` sotto. Se il valore anagrafico di una delle due unità
  (origine o destinazione) ricade in una categoria troppo generica per essere
  informativa (istituti comprensivi, convitti, o un valore non mappato) il
  vincolo di tipologia non si applica per quell'unità: resta solo il vincolo
  di `ordine_scuola`. Disattivabile con `--consenti-cambio-tipologia-scuola`
  come verifica di sensitività, non di default.
- codice_scuola diverso dall'origine (per costruzione le unità sopra soglia
  non possono comparire anche come destinazione, perché la destinazione deve
  avere p <= 0.30; vedi sotto).

LIMITE IMPORTANTE: il flusso MIM usato (ALUCORSOINDCLA / ALUITASTRACIT) non
contiene l'indirizzo di studio (es. liceo scientifico vs istituto tecnico
economico) per la secondaria di II grado. Questo limite è ora in parte
mitigato dal vincolo di tipologia sopra, che usa il valore anagrafico
(`DESCRIZIONETIPOLOGIAGRADOISTRUZIONESCUOLA`), disponibile per il 100% delle
unità nei dati attuali. Resta però un limite residuo noto: per le scuole
paritarie il valore anagrafico della secondaria II grado è spesso generico
("SCUOLA SEC. SECONDO GRADO NON STATALE", senza indirizzo specificato) e
quindi non vincolante — in quel caso, come per ogni valore non mappato, un
alunno di un liceo può in teoria essere abbinato a un istituto professionale
dello stesso anno di corso. Questo è dichiarato esplicitamente come limite
dei dati disponibili, non un'omissione di modellazione.

## Capacità delle sedi riceventi

Non esiste nei dati un campo di capienza massima. Si stima una capienza per
classe empirica come percentile (default: 95°) della distribuzione nazionale
di alunni/classi osservata per ciascuna coppia (tipo_gestione, ordine_scuola),
tra le unità con chiave classi/studenti confrontabile. La capienza stimata di
un'unità è `classi_esatte * capienza_classe_stimata`; i posti fisici
disponibili sono `max(0, capienza stimata - alunni_totali)`. Se
`classi_esatte` è vuoto, per la simulazione viene imputato il valore 1. Le
unità con meno di `MINIMO_ALUNNI` alunni totali sono escluse dall'analisi.

Una destinazione può inoltre ricevere al più
`floor((3*N - 10*F) / 7)` alunni non italiani aggiuntivi senza superare essa
stessa la soglia del 30% (stessa aritmetica esatta di `analyze.py`); il tetto
finale è il minimo tra capienza fisica e questo vincolo di soglia.

## Campionamento controfattuale (quota_campione)

Il criterio del 30% MIM riguarda la cittadinanza, non la competenza
linguistica. Poiché i dati non contengono alcuna misura di competenza in
italiano, `--quota-campione` (default 0.20) applica la simulazione di
spostamento realistico SOLO a un sottoinsieme casuale (Binomiale, seed fisso)
degli studenti individuati da `m_min` per ciascuna unità sopra soglia, come
PROXY PURAMENTE CONTROFATTUALE della quota che potrebbe non avere una
conoscenza adeguata dell'italiano. Non è una stima empirica: è un parametro
di scenario, chiaramente distinto dai dati osservati (colonna
`quota_campione` e `seed` in ogni output). Con `--quota-campione 1.0` si
ottiene lo scenario "pieno" (tutti gli `m_min`), utile come limite superiore
di confronto.

## Algoritmo di assegnazione

Per ciascun gruppo (tipo_gestione, ordine_scuola, anno_corso):
1. le unità di origine sono processate in un ordine che determina chi ha la
   priorità sui posti disponibili nelle destinazioni condivise dal gruppo. Di
   default l'ordine è deterministico (quota di non italiani decrescente, poi
   codice_scuola): priorità alle unità più sopra soglia. Non è un piano di
   assegnazione ottimale (servirebbe un problema di trasporto/flusso a costo
   minimo) ma un'euristica greedy trasparente e riproducibile. Con
   `--ordine-origine-casuale` l'ordine è invece una permutazione casuale
   (via seed) ricalcolata per ciascun gruppo: utile per una simulazione
   Monte Carlo sulla sensibilità del flusso di riallocazione all'ordine di
   elaborazione, che a parità di `quota_campione` (anche 1.00, cioè senza
   alcuna componente binomiale) può cambiare quali unità ottengono i posti
   più vicini quando più origini competono per le stesse destinazioni;
2. per ciascuna unità di origine, si cercano le destinazioni con posti
   disponibili più vicine (ricerca a griglia con anelli crescenti, filtrando
   per compatibilità del cluster di tipologia scolastica oltre che per
   capacità residua, poi distanza geodetica esatta - formula haversine,
   coordinate dal file di geocoding), assegnando gli studenti alle
   destinazioni più vicine finché la domanda campionata è soddisfatta o la
   capacità del gruppo è esaurita (in tal caso il residuo è "non
   riallocabile");
3. le capacità delle destinazioni si aggiornano man mano: due unità di
   origine vicine competono per gli stessi posti, chi viene processato prima
   (per severità) ha priorità.

La distanza è quella geodetica in linea d'aria (haversine) tra le coordinate
geocodificate dei due plessi, non la distanza stradale reale: è un limite
noto, riportato nei risultati.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data_processed"
RESULTS = ROOT / "results"
YEAR = "202425"
YEAR_LABEL = "2024/25"

UNITS_PATH = PROCESSED / f"unita_{YEAR}.csv"
GEOCODING_PATH = PROCESSED / f"geocoding_scuole_{YEAR}.csv"

EARTH_RADIUS_KM = 6371.0088
GRID_CELL_DEG = 0.25
RING_MARGIN = 2  # anelli extra esplorati dopo il primo che trova candidati,
                 # per attenuare l'effetto bordo-cella della griglia.

# Limite esplicito di alunni per classe. Se None, la simulazione usa la stima
# empirica al percentile configurato da --capienza-percentile.
MAX_LIMIT_PER_CLASS: int | None = 30

# Numero minimo di alunni totali perché un'unità partecipi alla simulazione.
MINIMO_ALUNNI = 10

# Mapping da valore anagrafico (DESCRIZIONETIPOLOGIAGRADOISTRUZIONESCUOLA,
# campo "tipo_scuola_anagrafe" in unita_202425.csv) a "cluster" di
# tipologia/indirizzo scolastico. Le categorie in IGNORED_SCHOOL_CLUSTERS sono
# definite troppo genericamente (organizzative, non un indirizzo specifico):
# le unità con quel valore, o con un valore anagrafico non presente qui
# affatto (es. le varianti "NON STATALE" delle paritarie, che non indicano
# l'indirizzo), non hanno un cluster e quindi nessun vincolo di tipologia,
# vedi TIPO_SCUOLA_TO_CLUSTER e cluster_compatible().
SCHOOL_TYPE_CLUSTERS: dict[str, list[str]] = {
    "primaria": [
        "SCUOLA PRIMARIA",
    ],
    "secondaria_primo_grado": [
        "SCUOLA PRIMO GRADO",
    ],
    "infanzia": [
        "SCUOLA INFANZIA",
    ],
    "commerciale_turistico_professionale": [
        "IST PROF PER I SERVIZI COMMERCIALI",
        "IST PROF PER I SERVIZI COMMERCIALI E TURISTICI",
        "IST PROF PER I SERVIZI TURISTICI",
        "IST PROF PER I SERVIZI COMM TUR E DELLA PUBB",
    ],
    "alberghiero_ristorazione": [
        "IST PROF PER I SERVIZI ALBERGHIERI E RISTORAZIONE",
        "IST PROF ALBERGHIERO",
    ],
    "agricoltura": [
        "IST PROF PER L'AGRICOLTURA E L'AMBIENTE",
        "IST PROF PER L'AGRICOLTURA",
        "ISTITUTO TECNICO AGRARIO",
    ],
    "industria_artigianato": [
        "IST PROF INDUSTRIA E ARTIGIANATO",
        "IST PROF INDUSTRIA E ARTIGIANATO PER CIECHI",
        "IST PROF INDUSTRIA E ARTIGIANATO PER SORDOMUTI",
    ],
    "commerciale_economico_tecnico": [
        "ISTITUTO TECNICO COMMERCIALE",
        "IST TEC COMMERCIALE E PER GEOMETRI",
        "IST TECNICO ECONOMICO E TECNOLOGICO",
    ],
    "geometri": [
        "ISTITUTO TECNICO PER GEOMETRI",
    ],
    "turismo_tecnico": [
        "ISTITUTO TECNICO PER IL TURISMO",
    ],
    "sociale": [
        "IST PROF PER I SERVIZI SOCIALI",
        "ISTITUTO TECNICO PER ATTIVITA' SOCIALI (GIA' ITF)",
    ],
    "artistico": [
        "LICEO ARTISTICO",
        "ISTITUTO D'ARTE",
    ],
    "magistrale": [
        "ISTITUTO MAGISTRALE",
        "SCUOLA MAGISTRALE",
    ],
    "nautico_marinare": [
        "ISTITUTO TECNICO NAUTICO",
        "IST PROF INDUSTRIA E ATTIVITA' MARINARE",
    ],
    "aeronautico": [
        "ISTITUTO TECNICO AERONAUTICO",
    ],
    "cinema_televisione_pubblicita": [
        "IST PROF CINEMATOGRAFIA E TELEVISIONE",
        "IST PROF PER I SERVIZI PUBBLICITARI",
    ],
    "industriale_tecnico": [
        "ISTITUTO TECNICO INDUSTRIALE",
    ],
    "liceo_classico": [
        "LICEO CLASSICO",
    ],
    "liceo_scientifico": [
        "LICEO SCIENTIFICO",
    ],
    # Tipologie organizzative, non identificano uno specifico insegnamento.
    "istituzioni_miste_o_generiche": [
        "ISTITUTO COMPRENSIVO",
        "ISTITUTO SUPERIORE",
        "CENTRO TERRITORIALE",
    ],
    "convitti_educandati": [
        "CONVITTO ANNESSO",
        "CONVITTO NAZIONALE",
        "EDUCANDATO",
    ],
}

IGNORED_SCHOOL_CLUSTERS = {"istituzioni_miste_o_generiche", "convitti_educandati"}

TIPO_SCUOLA_TO_CLUSTER: dict[str, str] = {
    raw_value: cluster_name
    for cluster_name, raw_values in SCHOOL_TYPE_CLUSTERS.items()
    if cluster_name not in IGNORED_SCHOOL_CLUSTERS
    for raw_value in raw_values
}


def cluster_compatible(src_cluster: str | None, dst_cluster: str | None) -> bool:
    """Nessun vincolo se uno dei due lati non ha un cluster di tipologia noto."""

    return src_cluster is None or dst_cluster is None or src_cluster == dst_cluster


DETAIL_FIELDS = [
    "anno_scolastico",
    "quota_campione",
    "seed",
    "tipo_gestione",
    "ordine_scuola",
    "anno_corso",
    "codice_scuola_origine",
    "denominazione_origine",
    "comune_origine",
    "provincia_origine",
    "regione_origine",
    "tipo_scuola_anagrafe_origine",
    "tipo_scuola_cluster_origine",
    "codice_scuola_destinazione",
    "denominazione_destinazione",
    "comune_destinazione",
    "provincia_destinazione",
    "regione_destinazione",
    "tipo_scuola_anagrafe_destinazione",
    "tipo_scuola_cluster_destinazione",
    "n_studenti_spostati",
    "distanza_km",
]

UNALLOCATED_FIELDS = [
    "anno_scolastico",
    "quota_campione",
    "seed",
    "tipo_gestione",
    "ordine_scuola",
    "anno_corso",
    "codice_scuola_origine",
    "denominazione_origine",
    "comune_origine",
    "provincia_origine",
    "regione_origine",
    "tipo_scuola_anagrafe_origine",
    "tipo_scuola_cluster_origine",
    "n_studenti_non_riallocati",
    "motivo",
]

CAPACITY_FIELDS = [
    "tipo_gestione",
    "ordine_scuola",
    "percentile_usato",
    "max_limit_per_class",
    "n_osservazioni",
    "capienza_classe_stimata",
]

QC_FIELDS = ["anno_scolastico", "quota_campione", "seed", "metrica", "valore", "nota"]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def haversine_km(lat1: float, lon1: float, lat2_arr: np.ndarray, lon2_arr: np.ndarray) -> np.ndarray:
    """Distanza geodetica (km) da un punto a un array di punti (radianti)."""

    dlat = lat2_arr - lat1
    dlon = lon2_arr - lon1
    a = np.sin(dlat / 2.0) ** 2 + math.cos(lat1) * np.cos(lat2_arr) * np.sin(dlon / 2.0) ** 2
    c = 2.0 * np.arcsin(np.minimum(1.0, np.sqrt(a)))
    return EARTH_RADIUS_KM * c


class Unit:
    __slots__ = (
        "tipo_gestione",
        "codice_scuola",
        "denominazione_scuola",
        "ordine_scuola",
        "anno_corso",
        "comune",
        "provincia",
        "regione",
        "tipo_scuola_anagrafe",
        "cluster",
        "alunni_italiani",
        "alunni_non_italiani",
        "alunni_totali",
        "sopra_30",
        "m_min",
        "irrisolvibile",
        "classi_esatte",
        "lat",
        "lon",
        "_capacity",
    )

    def __init__(self, row: dict[str, str]) -> None:
        self.tipo_gestione = row["tipo_gestione"]
        self.codice_scuola = row["codice_scuola"]
        self.denominazione_scuola = row["denominazione_scuola"]
        self.ordine_scuola = row["ordine_scuola"]
        self.anno_corso = row["anno_corso"]
        self.comune = row["comune"]
        self.provincia = row["provincia"]
        self.regione = row["regione"]
        self.tipo_scuola_anagrafe = row.get("tipo_scuola_anagrafe", "")
        self.cluster = TIPO_SCUOLA_TO_CLUSTER.get(self.tipo_scuola_anagrafe)
        self.alunni_italiani = int(row["alunni_italiani"])
        self.alunni_non_italiani = int(row["alunni_non_italiani"])
        self.alunni_totali = int(row["alunni_totali"])
        self.sopra_30 = row["sopra_30"] == "1"
        self.m_min = int(row["m_min"]) if row["m_min"] != "" else None
        self.irrisolvibile = row["m_min_irrisolvibile"] == "1"
        classi = (row.get("classi_esatte") or "").strip()
        self.classi_esatte = int(classi) if classi else 1
        self.lat = math.nan
        self.lon = math.nan


def load_units_with_coords() -> list[Unit]:
    rows = read_csv(UNITS_PATH)
    units = [
        Unit(row)
        for row in rows
        if row["anno_corso"] == "1" and int(row["alunni_totali"]) >= MINIMO_ALUNNI
    ]
    geo_rows = read_csv(GEOCODING_PATH)
    coords: dict[str, tuple[float, float]] = {}
    for row in geo_rows:
        code = row.get("codice_scuola", "").strip()
        lat_text = row.get("lat", "").strip()
        lon_text = row.get("lon", "").strip()
        if code and lat_text and lon_text:
            coords[code] = (float(lat_text), float(lon_text))
    missing = 0
    for unit in units:
        hit = coords.get(unit.codice_scuola)
        if hit is None:
            missing += 1
            continue
        unit.lat, unit.lon = hit
    return units, missing


def compute_capacity_table(
    units: list[Unit], percentile: float, *, write_output: bool = True
) -> dict[tuple[str, str], float]:
    """Capienza per classe fissa o stimata empiricamente per (gestione, ordine)."""

    if MAX_LIMIT_PER_CLASS is not None and (
        not isinstance(MAX_LIMIT_PER_CLASS, int)
        or isinstance(MAX_LIMIT_PER_CLASS, bool)
        or MAX_LIMIT_PER_CLASS <= 0
    ):
        raise ValueError("MAX_LIMIT_PER_CLASS deve essere un intero positivo oppure None")

    values: dict[tuple[str, str], list[float]] = defaultdict(list)
    for unit in units:
        if unit.classi_esatte and unit.classi_esatte > 0:
            values[(unit.tipo_gestione, unit.ordine_scuola)].append(
                unit.alunni_totali / unit.classi_esatte
            )
    table: dict[tuple[str, str], float] = {}
    rows_for_csv: list[dict[str, object]] = []
    for key, vals in sorted(values.items()):
        if MAX_LIMIT_PER_CLASS is None:
            arr = np.array(vals, dtype=float)
            cap = float(np.percentile(arr, percentile))
        else:
            cap = float(MAX_LIMIT_PER_CLASS)
        table[key] = cap
        rows_for_csv.append(
            {
                "tipo_gestione": key[0],
                "ordine_scuola": key[1],
                "percentile_usato": percentile if MAX_LIMIT_PER_CLASS is None else "",
                "max_limit_per_class": MAX_LIMIT_PER_CLASS if MAX_LIMIT_PER_CLASS is not None else "",
                "n_osservazioni": len(vals),
                "capienza_classe_stimata": round(cap, 3),
            }
        )
    if write_output:
        write_csv(PROCESSED / f"capienza_classe_stimata_{YEAR}.csv", rows_for_csv, CAPACITY_FIELDS)
    return table


def threshold_headroom(n: int, f: int) -> int:
    """Max alunni non italiani aggiuntivi ricevibili restando <= 0.30 (floor esatto)."""

    return (3 * n - 10 * f) // 7


def build_destination_index(
    destinations: list[Unit],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[tuple[int, int], list[int]]]:
    lat_rad = np.radians(np.array([d.lat for d in destinations], dtype=float))
    lon_rad = np.radians(np.array([d.lon for d in destinations], dtype=float))
    capacity = np.array([d._capacity for d in destinations], dtype=np.int64)  # type: ignore[attr-defined]
    grid: dict[tuple[int, int], list[int]] = defaultdict(list)
    for idx, d in enumerate(destinations):
        cell = (int(math.floor(d.lat / GRID_CELL_DEG)), int(math.floor(d.lon / GRID_CELL_DEG)))
        grid[cell].append(idx)
    return lat_rad, lon_rad, capacity, grid


def ring_cells(cx: int, cy: int, ring: int) -> list[tuple[int, int]]:
    if ring == 0:
        return [(cx, cy)]
    cells = []
    for dx in range(-ring, ring + 1):
        for dy in range(-ring, ring + 1):
            if max(abs(dx), abs(dy)) == ring:
                cells.append((cx + dx, cy + dy))
    return cells


def search_and_assign(
    source: Unit,
    needed: int,
    lat_rad: np.ndarray,
    lon_rad: np.ndarray,
    capacity: np.ndarray,
    grid: dict[tuple[int, int], list[int]],
    destinations: list[Unit],
    max_ring: int,
) -> tuple[list[tuple[int, float, int]], int]:
    """Ritorna (lista di (idx_destinazione, distanza_km, n_assegnati), residuo non allocato)."""

    if needed <= 0:
        return [], 0

    src_lat = math.radians(source.lat)
    src_lon = math.radians(source.lon)
    cx = int(math.floor(source.lat / GRID_CELL_DEG))
    cy = int(math.floor(source.lon / GRID_CELL_DEG))

    candidate_idx: list[int] = []
    found_first_at: int | None = None
    ring = 0
    while ring <= max_ring:
        for cell in ring_cells(cx, cy, ring):
            for idx in grid.get(cell, ()):
                if capacity[idx] > 0 and cluster_compatible(source.cluster, destinations[idx].cluster):
                    candidate_idx.append(idx)
        if candidate_idx and found_first_at is None:
            found_first_at = ring
        if found_first_at is not None:
            total_cap = int(capacity[candidate_idx].sum())
            if total_cap >= needed and ring >= found_first_at + RING_MARGIN:
                break
        ring += 1

    if not candidate_idx:
        return [], needed

    idx_arr = np.array(sorted(set(candidate_idx)), dtype=np.int64)
    dists = haversine_km(src_lat, src_lon, lat_rad[idx_arr], lon_rad[idx_arr])
    order = np.argsort(dists, kind="stable")
    idx_sorted = idx_arr[order]
    dist_sorted = dists[order]

    assignments: list[tuple[int, float, int]] = []
    remaining = needed
    for idx, dist in zip(idx_sorted, dist_sorted):
        if remaining <= 0:
            break
        avail = int(capacity[idx])
        if avail <= 0:
            continue
        take = min(avail, remaining)
        capacity[idx] -= take
        assignments.append((int(idx), float(dist), take))
        remaining -= take

    return assignments, remaining


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--quota-campione", type=float, default=0.20,
                         help="Quota casuale (0-1) del pool m_min effettivamente simulata (default 0.20).")
    parser.add_argument("--seed", type=int, default=42, help="Seed RNG per il campionamento (default 42).")
    parser.add_argument("--capienza-percentile", type=float, default=95.0,
                         help="Percentile empirico usato come capienza massima per classe (default 95).")
    parser.add_argument("--consenti-cambio-gestione", action="store_true",
                         help="Permette destinazioni con tipo_gestione diverso dall'origine (default: no).")
    parser.add_argument("--consenti-cambio-tipologia-scuola", action="store_true",
                         help="Disattiva il vincolo di cluster di tipologia/indirizzo scolastico "
                              "(derivato da DESCRIZIONETIPOLOGIAGRADOISTRUZIONESCUOLA); solo ordine_scuola "
                              "resta vincolante (default: no).")
    parser.add_argument("--ordine-origine-casuale", action="store_true",
                         help="Processa le unità di origine di ciascun gruppo in un ordine casuale "
                              "(permutazione via seed) invece dell'euristica per severità decrescente. "
                              "Usato per la simulazione Monte Carlo sulla sensibilità del flusso greedy "
                              "all'ordine di elaborazione (default: no, ordine deterministico).")
    parser.add_argument("--max-km", type=float, default=None,
                         help="Se impostato, oltre questa distanza (km) lo spostamento è considerato non realistico "
                              "e il residuo viene marcato non riallocabile invece di essere assegnato.")
    return parser.parse_args()


def run_simulation(
    args: argparse.Namespace,
    *,
    write_outputs: bool = True,
    print_summary: bool = True,
    detail_rows_out: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    if not (0.0 <= args.quota_campione <= 1.0):
        raise SystemExit("--quota-campione deve essere tra 0 e 1")

    units, missing_coords = load_units_with_coords()
    if missing_coords and print_summary:
        print(f"ATTENZIONE: {missing_coords} unità senza coordinate geocodificate, escluse.")
    units = [u for u in units if not math.isnan(u.lat) and not math.isnan(u.lon)]
    if args.consenti_cambio_tipologia_scuola:
        for u in units:
            u.cluster = None

    capacity_table = compute_capacity_table(units, args.capienza_percentile, write_output=write_outputs)

    # --- unità di origine ---
    all_above = [u for u in units if u.sopra_30]
    irrisolvibili = [u for u in all_above if u.irrisolvibile]
    sources_all = [u for u in all_above if not u.irrisolvibile and u.m_min and u.m_min > 0]

    rng = np.random.default_rng(args.seed)
    sampled: dict[str, int] = {}
    # Ordine di lettura del CSV (deterministico) per il campionamento: garantisce
    # riproducibilità del seed indipendente da qualunque riordinamento successivo.
    for u in sources_all:
        key = f"{u.tipo_gestione}|{u.codice_scuola}|{u.ordine_scuola}|{u.anno_corso}"
        sampled[key] = int(rng.binomial(u.m_min, args.quota_campione))

    # --- unità di destinazione ---
    destinations_all = [u for u in units if not u.sopra_30 and u.classi_esatte and u.classi_esatte > 0]
    excluded_no_classi = sum(
        1 for u in units if not u.sopra_30 and (not u.classi_esatte or u.classi_esatte <= 0)
    )
    for d in destinations_all:
        capacita_stimata = d.classi_esatte * capacity_table[(d.tipo_gestione, d.ordine_scuola)]
        posti_fisici = max(0, math.floor(capacita_stimata) - d.alunni_totali)
        posti_soglia = threshold_headroom(d.alunni_totali, d.alunni_non_italiani)
        d._capacity = max(0, min(posti_fisici, posti_soglia))  # type: ignore[attr-defined]
    destinations_all = [d for d in destinations_all if d._capacity > 0]  # type: ignore[attr-defined]

    def group_key(u: Unit, ignore_gestione: bool) -> tuple[str, str, str]:
        gestione = "*" if ignore_gestione else u.tipo_gestione
        return (gestione, u.ordine_scuola, u.anno_corso)

    dest_groups: dict[tuple[str, str, str], list[Unit]] = defaultdict(list)
    for d in destinations_all:
        dest_groups[group_key(d, args.consenti_cambio_gestione)].append(d)

    src_groups: dict[tuple[str, str, str], list[Unit]] = defaultdict(list)
    for u in sources_all:
        src_groups[group_key(u, args.consenti_cambio_gestione)].append(u)

    detail_rows: list[dict[str, object]] = []
    unallocated_rows: list[dict[str, object]] = []
    total_sampled = 0
    total_assigned = 0
    total_unallocated = 0
    all_distances: list[float] = []
    distances_by_order: dict[str, list[float]] = defaultdict(list)
    distances_by_region: dict[str, list[float]] = defaultdict(list)

    for gkey, group_sources in sorted(src_groups.items()):
        group_dests = dest_groups.get(gkey, [])
        if not group_dests:
            for u in group_sources:
                key = f"{u.tipo_gestione}|{u.codice_scuola}|{u.ordine_scuola}|{u.anno_corso}"
                needed = sampled[key]
                total_sampled += needed
                if needed > 0:
                    total_unallocated += needed
                    unallocated_rows.append(
                        {
                            "anno_scolastico": YEAR,
                            "quota_campione": args.quota_campione,
                            "seed": args.seed,
                            "tipo_gestione": u.tipo_gestione,
                            "ordine_scuola": u.ordine_scuola,
                            "anno_corso": u.anno_corso,
                            "codice_scuola_origine": u.codice_scuola,
                            "denominazione_origine": u.denominazione_scuola,
                            "comune_origine": u.comune,
                            "provincia_origine": u.provincia,
                            "regione_origine": u.regione,
                            "tipo_scuola_anagrafe_origine": u.tipo_scuola_anagrafe,
                            "tipo_scuola_cluster_origine": u.cluster or "",
                            "n_studenti_non_riallocati": needed,
                            "motivo": "nessuna_unita_ricevente_equivalente_nel_gruppo",
                        }
                    )
            continue

        lat_rad, lon_rad, capacity, grid = build_destination_index(group_dests)
        nrows_span = max(d.lat for d in group_dests) - min(d.lat for d in group_dests)
        ncols_span = max(d.lon for d in group_dests) - min(d.lon for d in group_dests)
        max_ring = int(max(nrows_span, ncols_span) / GRID_CELL_DEG) + 4
        dest_clusters_in_group = {d.cluster for d in group_dests}
        group_has_wildcard_dest = None in dest_clusters_in_group

        if args.ordine_origine_casuale:
            perm = rng.permutation(len(group_sources))
            ordered_sources = [group_sources[i] for i in perm]
        else:
            ordered_sources = sorted(
                group_sources,
                key=lambda u: (-(u.alunni_non_italiani / u.alunni_totali), u.codice_scuola),
            )
        for u in ordered_sources:
            key = f"{u.tipo_gestione}|{u.codice_scuola}|{u.ordine_scuola}|{u.anno_corso}"
            needed = sampled[key]
            total_sampled += needed
            if needed <= 0:
                continue
            assignments, leftover = search_and_assign(
                u, needed, lat_rad, lon_rad, capacity, grid, group_dests, max_ring
            )
            for idx, dist, take in assignments:
                if args.max_km is not None and dist > args.max_km:
                    leftover += take
                    capacity[idx] += take  # rilascia il posto, non realisticamente raggiungibile
                    continue
                dest = group_dests[idx]
                detail_rows.append(
                    {
                        "anno_scolastico": YEAR,
                        "quota_campione": args.quota_campione,
                        "seed": args.seed,
                        "tipo_gestione": u.tipo_gestione,
                        "ordine_scuola": u.ordine_scuola,
                        "anno_corso": u.anno_corso,
                        "codice_scuola_origine": u.codice_scuola,
                        "denominazione_origine": u.denominazione_scuola,
                        "comune_origine": u.comune,
                        "provincia_origine": u.provincia,
                        "regione_origine": u.regione,
                        "tipo_scuola_anagrafe_origine": u.tipo_scuola_anagrafe,
                        "tipo_scuola_cluster_origine": u.cluster or "",
                        "codice_scuola_destinazione": dest.codice_scuola,
                        "denominazione_destinazione": dest.denominazione_scuola,
                        "comune_destinazione": dest.comune,
                        "provincia_destinazione": dest.provincia,
                        "regione_destinazione": dest.regione,
                        "tipo_scuola_anagrafe_destinazione": dest.tipo_scuola_anagrafe,
                        "tipo_scuola_cluster_destinazione": dest.cluster or "",
                        "n_studenti_spostati": take,
                        "distanza_km": round(dist, 3),
                    }
                )
                total_assigned += take
                all_distances.extend([dist] * take)
                distances_by_order[u.ordine_scuola].extend([dist] * take)
                distances_by_region[u.regione].extend([dist] * take)
            if leftover > 0:
                total_unallocated += leftover
                if u.cluster is not None and not group_has_wildcard_dest and u.cluster not in dest_clusters_in_group:
                    motivo = "nessuna_destinazione_tipologia_compatibile_nel_gruppo"
                elif args.max_km is None:
                    motivo = "capacita_esaurita_nel_gruppo_nazionale"
                else:
                    motivo = "capacita_esaurita_o_oltre_max_km"
                unallocated_rows.append(
                    {
                        "anno_scolastico": YEAR,
                        "quota_campione": args.quota_campione,
                        "seed": args.seed,
                        "tipo_gestione": u.tipo_gestione,
                        "ordine_scuola": u.ordine_scuola,
                        "anno_corso": u.anno_corso,
                        "codice_scuola_origine": u.codice_scuola,
                        "denominazione_origine": u.denominazione_scuola,
                        "comune_origine": u.comune,
                        "provincia_origine": u.provincia,
                        "regione_origine": u.regione,
                        "tipo_scuola_anagrafe_origine": u.tipo_scuola_anagrafe,
                        "tipo_scuola_cluster_origine": u.cluster or "",
                        "n_studenti_non_riallocati": leftover,
                        "motivo": motivo,
                    }
                )

    suffix = f"q{int(round(args.quota_campione * 100)):03d}_seed{args.seed}"
    if args.ordine_origine_casuale:
        suffix += "_ordcas"
    if write_outputs:
        write_csv(
            RESULTS / f"simulazione_spostamenti_dettaglio_{YEAR}_{suffix}.csv", detail_rows, DETAIL_FIELDS
        )
        write_csv(
            RESULTS / f"simulazione_non_riallocabili_{YEAR}_{suffix}.csv", unallocated_rows, UNALLOCATED_FIELDS
        )

    # --- controlli di qualità ---
    qc_rows: list[dict[str, object]] = []

    def qc(metric: str, value: object, note: str = "") -> None:
        qc_rows.append(
            {
                "anno_scolastico": YEAR,
                "quota_campione": args.quota_campione,
                "seed": args.seed,
                "metrica": metric,
                "valore": value,
                "nota": note,
            }
        )

    # Ricostruzione capacità finale delle destinazioni per verificare soglia e capienza.
    assigned_by_dest: dict[str, int] = defaultdict(int)
    for row in detail_rows:
        assigned_by_dest[row["codice_scuola_destinazione"], row["ordine_scuola"], row["anno_corso"]] += row[
            "n_studenti_spostati"
        ]
    dest_index = {(d.codice_scuola, d.ordine_scuola, d.anno_corso): d for d in destinations_all}
    violazioni_soglia = 0
    violazioni_capacita = 0
    for key, assigned in assigned_by_dest.items():
        d = dest_index[key]
        original_capacity = d._capacity  # type: ignore[attr-defined]
        if assigned > original_capacity:
            violazioni_capacita += 1
        new_f = d.alunni_non_italiani + assigned
        new_n = d.alunni_totali + assigned
        if 10 * new_f > 3 * new_n:
            violazioni_soglia += 1

    violazioni_tipologia_scuola = sum(
        1
        for row in detail_rows
        if not cluster_compatible(
            row["tipo_scuola_cluster_origine"] or None, row["tipo_scuola_cluster_destinazione"] or None
        )
    )

    balance_errors = 0
    assigned_by_source: dict[str, int] = defaultdict(int)
    for row in detail_rows:
        assigned_by_source[
            row["codice_scuola_origine"], row["ordine_scuola"], row["anno_corso"]
        ] += row["n_studenti_spostati"]
    unallocated_by_source: dict[str, int] = defaultdict(int)
    for row in unallocated_rows:
        unallocated_by_source[
            row["codice_scuola_origine"], row["ordine_scuola"], row["anno_corso"]
        ] += row["n_studenti_non_riallocati"]
    for u in sources_all:
        key = f"{u.tipo_gestione}|{u.codice_scuola}|{u.ordine_scuola}|{u.anno_corso}"
        needed = sampled[key]
        got = assigned_by_source.get((u.codice_scuola, u.ordine_scuola, u.anno_corso), 0)
        unalloc = unallocated_by_source.get((u.codice_scuola, u.ordine_scuola, u.anno_corso), 0)
        if got + unalloc != needed:
            balance_errors += 1

    qc("unita_sopra_30_totali", len(all_above))
    qc("classi_sopra_30_totali", sum(u.classi_esatte for u in all_above),
       "Somma di classi_esatte delle unità sopra soglia, non conteggio di unità.")
    qc("unita_sopra_30_irrisolvibili_escluse", len(irrisolvibili),
       "Zero alunni italiani: escluse dalla simulazione, vedi analyze.py")
    qc("unita_destinazione_candidate", len(destinations_all))
    qc("unita_destinazione_escluse_senza_classi_esatte", excluded_no_classi)
    qc("studenti_campionati_totale", total_sampled)
    qc("studenti_riallocati_totale", total_assigned)
    qc("studenti_non_riallocati_totale", total_unallocated)
    qc("violazioni_soglia_30_in_destinazioni", violazioni_soglia,
       "Deve essere 0: nessuna destinazione può superare 0.30 dopo l'inserimento.")
    qc("violazioni_capacita_in_destinazioni", violazioni_capacita,
       "Deve essere 0: nessuna destinazione può ricevere più della propria capacità stimata.")
    qc("violazioni_tipologia_scuola_in_destinazioni", violazioni_tipologia_scuola,
       "Deve essere 0: nessun abbinamento può avere cluster di tipologia scolastica incompatibili.")
    qc("unita_origine_con_bilancio_incoerente", balance_errors,
       "Deve essere 0: assegnati + non_riallocati deve sempre coincidere col campione.")
    qc("capienza_percentile_usato", args.capienza_percentile if MAX_LIMIT_PER_CLASS is None else "nessuno")
    qc("max_limit_per_class_usato", MAX_LIMIT_PER_CLASS if MAX_LIMIT_PER_CLASS is not None else "nessuno")
    qc("cambio_gestione_consentito", int(args.consenti_cambio_gestione))
    qc("cluster_tipologia_scuola_applicato", int(not args.consenti_cambio_tipologia_scuola))
    qc("ordine_origine_casuale", int(args.ordine_origine_casuale))
    qc("max_km_applicato", args.max_km if args.max_km is not None else "nessuno")

    if write_outputs:
        write_csv(RESULTS / f"controlli_qualita_simulazione_{YEAR}_{suffix}.csv", qc_rows, QC_FIELDS)

    # --- distribuzione delle distanze (bin per istogramma) ---
    dist_rows: list[dict[str, object]] = []
    if all_distances:
        arr = np.array(all_distances)
        bin_edges = [0, 1, 2, 5, 10, 20, 30, 50, 75, 100, 150, 200, 300, 500, 750, 1000, float("inf")]
        for lo, hi in zip(bin_edges[:-1], bin_edges[1:]):
            count = int(np.sum((arr >= lo) & (arr < hi)))
            label = f"[{lo},{hi})" if hi != float("inf") else f"[{lo},+inf)"
            dist_rows.append({"bin_km": label, "n_studenti": count})
    if write_outputs:
        write_csv(
            RESULTS / f"simulazione_distribuzione_distanze_{YEAR}_{suffix}.csv",
            dist_rows,
            ["bin_km", "n_studenti"],
        )

    def dist_stats(values: list[float]) -> dict[str, float | int]:
        if not values:
            return {"n": 0}
        arr = np.array(values)
        return {
            "n": len(values),
            "media_km": round(float(arr.mean()), 3),
            "mediana_km": round(float(np.median(arr)), 3),
            "p90_km": round(float(np.percentile(arr, 90)), 3),
            "p95_km": round(float(np.percentile(arr, 95)), 3),
            "max_km": round(float(arr.max()), 3),
            "min_km": round(float(arr.min()), 3),
        }

    summary = {
        "generated_on": __import__("datetime").date.today().isoformat(),
        "school_year": YEAR_LABEL,
        "quota_campione": args.quota_campione,
        "seed": args.seed,
        "capienza_percentile": args.capienza_percentile if MAX_LIMIT_PER_CLASS is None else None,
        "max_limit_per_class": MAX_LIMIT_PER_CLASS,
        "consenti_cambio_gestione": args.consenti_cambio_gestione,
        "consenti_cambio_tipologia_scuola": args.consenti_cambio_tipologia_scuola,
        "ordine_origine_casuale": args.ordine_origine_casuale,
        "max_km_applicato": args.max_km,
        "nota_campionamento": (
            "quota_campione applica un campionamento Binomiale(m_min, quota_campione) "
            "riproducibile via seed sul pool m_min di analyze.py (formula senza sostituzione). "
            "E' uno scenario controfattuale (proxy della quota senza adeguata conoscenza "
            "dell'italiano), non una misura osservata."
        ),
        # Totali sulle unità in simulazione (escluse quelle senza coordinate).
        "alunni_italiani_totale": sum(u.alunni_italiani for u in units),
        "alunni_non_italiani_totale": sum(u.alunni_non_italiani for u in units),
        "unita_sopra_30_totali": len(all_above),
        "classi_sopra_30_totali": sum(u.classi_esatte for u in all_above),
        "unita_sopra_30_irrisolvibili_escluse": len(irrisolvibili),
        "unita_destinazione_candidate": len(destinations_all),
        "studenti_m_min_pool_totale": sum(u.m_min for u in sources_all),
        "studenti_campionati_totale": total_sampled,
        "studenti_riallocati_totale": total_assigned,
        "studenti_non_riallocati_totale": total_unallocated,
        "quota_riallocati_su_campionati": round(total_assigned / total_sampled, 4) if total_sampled else None,
        "distanza_km": dist_stats(all_distances),
        "distanza_km_per_ordine_scuola": {k: dist_stats(v) for k, v in sorted(distances_by_order.items())},
        "distanza_km_per_regione": {k: dist_stats(v) for k, v in sorted(distances_by_region.items())},
        "controlli_qualita": {str(row["metrica"]): row["valore"] for row in qc_rows},
    }
    if write_outputs:
        RESULTS.mkdir(parents=True, exist_ok=True)
        (RESULTS / f"simulazione_riepilogo_{YEAR}_{suffix}.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    if print_summary:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    if detail_rows_out is not None:
        detail_rows_out.extend(detail_rows)
    return summary


def main() -> None:
    run_simulation(parse_args())


if __name__ == "__main__":
    main()
