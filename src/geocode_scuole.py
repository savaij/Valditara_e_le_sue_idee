#!/usr/bin/env python3
"""Geocoding delle anagrafiche scuole MIM tramite Google Geocoding API v4.

Dipendenze: sola libreria standard Python 3.10+ (la chiave API è letta da .env).

Legge le quattro anagrafiche (statale/paritaria standard e delle province
autonome), costruisce per ogni plesso una stringa di indirizzo a partire dai
campi strutturati del CSV e chiede a Google le coordinate. Le richieste sono
deduplicate per indirizzo e memorizzate in una cache su disco: in caso di
interruzione o errore basta rilanciare lo script per riprendere da dove si era
fermato senza ripetere le chiamate già andate a buon fine.

Endpoint: https://geocode.googleapis.com/v4/geocode/address/{ADDRESS}?key=...
Google restituisce quasi sempre un risultato, anche per input imperfetti: la
precisione effettiva va letta dal campo `granularity` (ROOFTOP >
RANGE_INTERPOLATED > GEOMETRIC_CENTER > APPROXIMATE), riportato nell'output.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data_raw"
PROCESSED = ROOT / "data_processed"
ENV_PATH = ROOT / ".env"

CACHE_PATH = PROCESSED / "geocoding_cache.json"
OUTPUT_PATH = PROCESSED / "geocoding_scuole_202425.csv"

GEOCODE_URL = "https://geocode.googleapis.com/v4/geocode/address/"
DEFAULT_WORKERS = 5
FLUSH_EVERY = 200  # salva la cache ogni N nuove chiamate

# I quattro file di input e la relativa etichetta di fonte.
INPUT_FILES = [
    ("SCUANAGRAFESTAT20242520250831.csv", "statale"),
    ("SCUANAGRAFEPAR20242520250831.csv", "paritaria"),
    ("SCUANAAUTSTAT20242520250831.csv", "statale_autonoma"),
    ("SCUANAAUTPAR20242520250831.csv", "paritaria_autonoma"),
]

MISSING_VALUES = {"", "non disponibile", "nd", "n.d."}

OUTPUT_FIELDS = [
    "codice_scuola",
    "fonte_anagrafe",
    "denominazione_scuola",
    "indirizzo_scuola",
    "cap_scuola",
    "comune",
    "provincia",
    "regione",
    "query_usata",
    "livello_geocoding",
    "lat",
    "lon",
    "granularita",
    "formatted_address",
    "place_id",
]


def load_api_key() -> str:
    """Legge GOOGLE_API dall'ambiente o dal file .env."""
    key = os.environ.get("GOOGLE_API")
    if not key and ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("GOOGLE_API=") and not line.startswith("#"):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
                break
    if not key:
        sys.exit("ERRORE: GOOGLE_API non trovata né nell'ambiente né in .env")
    return key


def is_missing(value: str | None) -> bool:
    return value is None or value.strip().lower() in MISSING_VALUES


def clean_comune(descrizione: str) -> str:
    """Normalizza DESCRIZIONECOMUNE.

    I comuni bilingui arrivano come "SILANDRO * SCHLANDERS": si tiene la prima
    denominazione, che è quella italiana usata anche altrove.
    """
    if not descrizione:
        return ""
    return descrizione.split("*")[0].strip()


class SchoolRecord:
    __slots__ = (
        "codice_scuola",
        "fonte",
        "denominazione",
        "indirizzo",
        "cap",
        "comune",
        "provincia",
        "regione",
    )

    def __init__(self, row: dict[str, str], fonte: str) -> None:
        self.codice_scuola = (row.get("CODICESCUOLA") or "").strip()
        self.fonte = fonte
        self.denominazione = (row.get("DENOMINAZIONESCUOLA") or "").strip()
        self.indirizzo = (row.get("INDIRIZZOSCUOLA") or "").strip()
        self.cap = (row.get("CAPSCUOLA") or "").strip()
        self.comune = clean_comune((row.get("DESCRIZIONECOMUNE") or "").strip())
        self.provincia = (row.get("PROVINCIA") or "").strip()
        self.regione = (row.get("REGIONE") or "").strip()

    def build_query(self, include_name: bool = False) -> tuple[str, str]:
        """Restituisce (stringa indirizzo, livello di geocoding richiesto).

        Con i campi strutturati del CSV si compone una singola stringa
        free-form: Google gestisce bene abbreviazioni e civici. Se l'indirizzo
        manca (tipico delle province autonome) si usa il solo comune.
        Se `include_name` è attivo, la denominazione della scuola viene
        anteposta alla query per aiutare la disambiguazione.
        """
        parts: list[str] = []
        livello = "comune"
        if include_name and not is_missing(self.denominazione):
            parts.append(self.denominazione)
        if not is_missing(self.indirizzo):
            parts.append(self.indirizzo)
            livello = "indirizzo"
        citta = self.comune
        if not is_missing(self.cap):
            citta = f"{self.cap} {citta}".strip()
        if citta:
            parts.append(citta)
        if self.provincia:
            parts.append(self.provincia)
        parts.append("Italia")
        return ", ".join(p for p in parts if p), livello


def load_cache() -> dict[str, dict | None]:
    if CACHE_PATH.exists():
        with CACHE_PATH.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def save_cache(cache: dict[str, dict | None]) -> None:
    """Scrittura atomica: prima su file temporaneo, poi rename."""
    PROCESSED.mkdir(parents=True, exist_ok=True)
    tmp = CACHE_PATH.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(cache, fh, ensure_ascii=False, indent=0)
    tmp.replace(CACHE_PATH)


def read_records() -> list[SchoolRecord]:
    records: list[SchoolRecord] = []
    seen: set[str] = set()
    for filename, fonte in INPUT_FILES:
        path = RAW / filename
        if not path.exists():
            print(f"ATTENZIONE: file mancante, saltato: {path}", file=sys.stderr)
            continue
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                rec = SchoolRecord(row, fonte)
                if not rec.codice_scuola or rec.codice_scuola in seen:
                    continue
                seen.add(rec.codice_scuola)
                records.append(rec)
    return records


def google_request(address: str, api_key: str) -> dict | None:
    """Chiama Google Geocoding v4 e restituisce il primo risultato o None.

    Solleva l'eccezione di rete/HTTP al chiamante per gestire i retry.
    """
    path = urllib.parse.quote(address, safe="")
    params = urllib.parse.urlencode({"key": api_key, "regionCode": "it", "languageCode": "it"})
    url = f"{GEOCODE_URL}{path}?{params}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)
    results = payload.get("results") or []
    if not results:
        return None
    hit = results[0]
    loc = hit.get("location") or {}
    return {
        "lat": loc.get("latitude"),
        "lon": loc.get("longitude"),
        "granularity": hit.get("granularity"),
        "formatted_address": hit.get("formattedAddress"),
        "place_id": hit.get("placeId"),
    }


RETRYABLE_HTTP_CODES = {429, 500, 502, 503, 504}
BACKOFF_BASE = 1.0  # secondi
BACKOFF_MAX = 60.0  # tetto per singola attesa
BACKOFF_JITTER = 0.5  # frazione di jitter casuale aggiunta al delay


def _retry_after_seconds(exc: urllib.error.HTTPError) -> float | None:
    """Legge l'header Retry-After (in secondi) se Google lo fornisce."""
    header = exc.headers.get("Retry-After") if exc.headers else None
    if not header:
        return None
    try:
        return float(header)
    except ValueError:
        return None


def geocode_with_retry(address: str, api_key: str, max_retries: int = 5) -> dict | None:
    """Chiama Google con backoff esponenziale sugli errori transitori.

    Il delay raddoppia ad ogni tentativo (1s, 2s, 4s, ...) fino a BACKOFF_MAX,
    con un jitter casuale per evitare che i thread paralleli si risincronizzino
    sugli stessi istanti di retry. Sui 429 si rispetta l'header Retry-After
    quando Google lo restituisce.
    """
    for attempt in range(1, max_retries + 1):
        try:
            return google_request(address, api_key)
        except urllib.error.HTTPError as exc:
            # 429 = quota, 5xx = transitorio lato server.
            if exc.code in RETRYABLE_HTTP_CODES and attempt < max_retries:
                delay = _retry_after_seconds(exc)
                if delay is None:
                    delay = min(BACKOFF_BASE * (2 ** (attempt - 1)), BACKOFF_MAX)
                    delay += random.uniform(0, delay * BACKOFF_JITTER)
                time.sleep(delay)
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            if attempt < max_retries:
                delay = min(BACKOFF_BASE * (2 ** (attempt - 1)), BACKOFF_MAX)
                delay += random.uniform(0, delay * BACKOFF_JITTER)
                time.sleep(delay)
                continue
            raise
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None, help="Max scuole (per test).")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help="Thread paralleli.")
    parser.add_argument(
        "--name",
        action="store_true",
        help="Include la denominazione della scuola nella query di geocoding.",
    )
    args = parser.parse_args()

    api_key = load_api_key()
    records = read_records()
    if args.limit is not None:
        records = records[: args.limit]
    print(f"Scuole da geocodificare: {len(records)}")

    cache = load_cache()
    print(f"Voci già in cache: {len(cache)}")

    # Indirizzi unici ancora da richiedere (deduplicati).
    queries = {rec.build_query(args.name)[0] for rec in records}
    todo = sorted(q for q in queries if q not in cache)
    print(f"Indirizzi unici: {len(queries)} | da richiedere: {len(todo)}")

    cache_lock = threading.Lock()
    done = 0
    errors = 0
    try:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(geocode_with_retry, q, api_key): q for q in todo}
            for fut in as_completed(futures):
                query = futures[fut]
                try:
                    result = fut.result()
                except Exception as exc:  # noqa: BLE001
                    errors += 1
                    print(f"  ERRORE su [{query}]: {exc}", file=sys.stderr)
                    continue
                with cache_lock:
                    cache[query] = result
                    done += 1
                    if done % FLUSH_EVERY == 0:
                        save_cache(cache)
                        print(f"  {done}/{len(todo)} completati, cache salvata "
                              f"({len(cache)} voci, {errors} errori)")
    except KeyboardInterrupt:
        print("\nInterruzione: salvo la cache prima di uscire...", file=sys.stderr)
    finally:
        save_cache(cache)

    print(f"Geocoding completato. Nuove chiamate riuscite: {done}, errori: {errors}. "
          f"Cache: {len(cache)} voci.")

    # Scrittura dell'output CSV unendo i record alle coordinate in cache.
    PROCESSED.mkdir(parents=True, exist_ok=True)
    found = 0
    with OUTPUT_PATH.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        for rec in records:
            query, livello = rec.build_query(args.name)
            hit = cache.get(query)
            if hit:
                found += 1
            writer.writerow(
                {
                    "codice_scuola": rec.codice_scuola,
                    "fonte_anagrafe": rec.fonte,
                    "denominazione_scuola": rec.denominazione,
                    "indirizzo_scuola": rec.indirizzo,
                    "cap_scuola": rec.cap,
                    "comune": rec.comune,
                    "provincia": rec.provincia,
                    "regione": rec.regione,
                    "query_usata": query,
                    "livello_geocoding": livello if hit else "nessuno",
                    "lat": (hit or {}).get("lat", ""),
                    "lon": (hit or {}).get("lon", ""),
                    "granularita": (hit or {}).get("granularity", ""),
                    "formatted_address": (hit or {}).get("formatted_address", ""),
                    "place_id": (hit or {}).get("place_id", ""),
                }
            )
    print(f"Scritto {OUTPUT_PATH} ({found}/{len(records)} scuole con coordinate).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
