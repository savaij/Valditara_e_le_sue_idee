#!/usr/bin/env python3
"""Create an interactive map of the analysed school campuses.

The map joins the rows in ``aggregati_202425.csv`` corresponding to
``livello_aggregazione == "plesso"`` and ``tipo_gestione == "tutte"`` with
the coordinates in ``geocoding_scuole_202425.csv`` using ``codice_scuola``.

The generated HTML is self-contained apart from the Leaflet JavaScript/CSS
and the Esri basemap tiles, which are loaded from their public services when
the file is opened in a browser.  No Python mapping package is required.

Circle sizes are HTML marker radii measured in screen pixels rather than
metres.  This keeps them from becoming tiny or enormous when the map is
zoomed.  The radius is also clamped to a readable range and scales with the
square root of ``m_min_sopra_30`` so that the area of a circle is approximately
proportional to the value.  Leaflet.markercluster groups those markers when
the map is zoomed out and expands them as the user zooms in.

Usage from the project root::

    python src/plot_schools.py

Optional paths can be supplied for testing or for a different run::

    python src/plot_schools.py --aggregates ... --geocoding ... --output ...
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AGGREGATES = ROOT / "results" / "aggregati_202425.csv"
DEFAULT_GEOCODING = ROOT / "data_processed" / "geocoding_scuole_202425.csv"
DEFAULT_OUTPUT = ROOT / "results" / "mappa_scuole_202425.html"

LEAFLET_VERSION = "1.9.4"
MARKERCLUSTER_VERSION = "1.5.3"
MIN_RADIUS_PX = 3.0
MAX_RADIUS_PX = 14.0
TILE_URL = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/"
    "MapServer/tile/{z}/{y}/{x}"
)
TILE_ATTRIBUTION = (
    "Sources: Esri, DeLorme, HERE, Garmin, USGS, Intermap, INCREMENT P, "
    "NRCan, Esri Japan, METI, Esri China (Hong Kong), MapmyIndia, TomTom"
)

AGGREGATE_FIELDS = {
    "livello_aggregazione",
    "tipo_gestione",
    "codice_scuola",
    "denominazione_scuola",
    "regione",
    "provincia",
    "comune",
    "m_min_sopra_30",
    "unita_totali",
    "unita_sopra_30",
    "studenti_totali_sopra_30",
    "studenti_non_italiani_sopra_30",
}
GEOCODING_FIELDS = {"codice_scuola", "lat", "lon", "granularita", "formatted_address"}


def read_csv(path: Path) -> list[dict[str, str]]:
    """Read a UTF-8 CSV and preserve identifiers as strings."""

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def require_fields(path: Path, rows: list[dict[str, str]], fields: set[str]) -> None:
    """Raise a useful error when an input does not have the expected schema."""

    actual = set(rows[0]) if rows else set()
    missing = sorted(fields - actual)
    if missing:
        raise ValueError(f"{path}: colonne mancanti: {', '.join(missing)}")


def as_float(value: str, field: str, code: str, path: Path) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{path}: {field} non numerico per {code!r}: {value!r}") from exc
    if not math.isfinite(number):
        raise ValueError(f"{path}: {field} non finito per {code!r}: {value!r}")
    return number


def as_nonnegative_int(value: str, field: str, code: str, path: Path) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{path}: {field} non intero per {code!r}: {value!r}") from exc
    if number < 0:
        raise ValueError(f"{path}: {field} negativo per {code!r}: {number}")
    return number


def load_target_rows(aggregates_path: Path) -> dict[str, dict[str, str]]:
    """Load one aggregate row per analysed plesso in the combined population."""

    rows = read_csv(aggregates_path)
    require_fields(aggregates_path, rows, AGGREGATE_FIELDS)
    selected = {
        row["codice_scuola"].strip(): row
        for row in rows
        if row.get("livello_aggregazione", "").strip() == "plesso"
        and row.get("tipo_gestione", "").strip() == "tutte"
        and row.get("codice_scuola", "").strip()
    }
    if not selected:
        raise ValueError(
            f"{aggregates_path}: nessuna riga con livello_aggregazione=plesso "
            "e tipo_gestione=tutte"
        )

    # The selected aggregation should have one row per school code.  Failing
    # loudly here prevents a silent loss caused by a dictionary overwrite if
    # the aggregation definition changes in the future.
    selected_rows = [
        row
        for row in rows
        if row.get("livello_aggregazione", "").strip() == "plesso"
        and row.get("tipo_gestione", "").strip() == "tutte"
        and row.get("codice_scuola", "").strip()
    ]
    if len(selected) != len(selected_rows):
        duplicates = sorted(
            code
            for code in {
                row["codice_scuola"].strip() for row in selected_rows
            }
            if sum(row["codice_scuola"].strip() == code for row in selected_rows) > 1
        )
        raise ValueError(
            f"{aggregates_path}: codici scuola duplicati nel sottoinsieme target: "
            f"{', '.join(duplicates[:10])}"
        )
    return selected


def load_geocoding_rows(geocoding_path: Path) -> dict[str, dict[str, str]]:
    """Load geocoding records indexed by school code."""

    rows = read_csv(geocoding_path)
    require_fields(geocoding_path, rows, GEOCODING_FIELDS)
    indexed: dict[str, dict[str, str]] = {}
    for row in rows:
        code = row.get("codice_scuola", "").strip()
        if not code:
            continue
        if code in indexed:
            raise ValueError(f"{geocoding_path}: codice_scuola duplicato: {code}")
        indexed[code] = row
    return indexed


def join_rows(
    target: dict[str, dict[str, str]],
    geocoding: dict[str, dict[str, str]],
    geocoding_path: Path,
    aggregates_path: Path,
) -> tuple[list[dict[str, object]], int, int]:
    """Join aggregates to coordinates and skip records without usable coords."""

    joined: list[dict[str, object]] = []
    missing_geocoding: list[str] = []
    missing_coordinates: list[str] = []
    for code, aggregate in target.items():
        geo = geocoding.get(code)
        if geo is None:
            missing_geocoding.append(code)
            continue
        lat_text = geo.get("lat", "").strip()
        lon_text = geo.get("lon", "").strip()
        if not lat_text or not lon_text:
            missing_coordinates.append(code)
            continue

        lat = as_float(lat_text, "lat", code, geocoding_path)
        lon = as_float(lon_text, "lon", code, geocoding_path)
        m_min = as_nonnegative_int(
            aggregate["m_min_sopra_30"], "m_min_sopra_30", code, aggregates_path
        )
        joined.append(
            {
                "code": code,
                "name": aggregate["denominazione_scuola"].strip(),
                "comune": aggregate["comune"].strip(),
                "provincia": aggregate["provincia"].strip(),
                "regione": aggregate["regione"].strip(),
                "lat": lat,
                "lon": lon,
                "m_min": m_min,
                "unita_totali": as_nonnegative_int(
                    aggregate["unita_totali"], "unita_totali", code, aggregates_path
                ),
                "unita_sopra_30": as_nonnegative_int(
                    aggregate["unita_sopra_30"], "unita_sopra_30", code, aggregates_path
                ),
                "studenti_totali_sopra_30": as_nonnegative_int(
                    aggregate["studenti_totali_sopra_30"],
                    "studenti_totali_sopra_30",
                    code,
                    aggregates_path,
                ),
                "studenti_non_italiani_sopra_30": as_nonnegative_int(
                    aggregate["studenti_non_italiani_sopra_30"],
                    "studenti_non_italiani_sopra_30",
                    code,
                    aggregates_path,
                ),
                "granularita": geo.get("granularita", "").strip(),
                "formatted_address": geo.get("formatted_address", "").strip(),
            }
        )

    if missing_geocoding:
        print(
            f"ATTENZIONE: {len(missing_geocoding)} plessi senza riga nel file "
            f"di geocoding; esempi: {', '.join(missing_geocoding[:5])}",
            file=sys.stderr,
        )
    if missing_coordinates:
        print(
            f"ATTENZIONE: {len(missing_coordinates)} plessi senza coordinate "
            f"utilizzabili; esempi: {', '.join(missing_coordinates[:5])}",
            file=sys.stderr,
        )
    if not joined:
        raise ValueError("Nessun plesso del sottoinsieme target ha coordinate utilizzabili")
    return joined, len(missing_geocoding), len(missing_coordinates)


def javascript_data(rows: list[dict[str, object]]) -> str:
    """Serialize data safely for embedding in a script tag."""

    # Prevent a school name containing </script> from terminating the script.
    return json.dumps(rows, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def build_html(
    rows: list[dict[str, object]],
    target_count: int,
    excluded_zero: int,
    missing_geocoding: int,
    missing_coordinates: int,
) -> str:
    values = [int(row["m_min"]) for row in rows]
    maximum = max(values) if values else 0
    data = javascript_data(rows)
    summary = json.dumps(
        {
            "plessi_target": target_count,
            "plessi_plottati": len(rows),
            "esclusi_m_min_zero": excluded_zero,
            "senza_geocoding": missing_geocoding,
            "senza_coordinate": missing_coordinates,
            "m_min_max": maximum,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return f"""<!doctype html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Scuole MIM 2024/25 — mappa del criterio del 30%</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@{LEAFLET_VERSION}/dist/leaflet.css"
        crossorigin="">
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/leaflet.markercluster@{MARKERCLUSTER_VERSION}/dist/MarkerCluster.css">
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/leaflet.markercluster@{MARKERCLUSTER_VERSION}/dist/MarkerCluster.Default.css">
  <style>
    html, body, #map {{ height: 100%; margin: 0; }}
    body {{ font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }}
    .map-title, .map-legend {{
      background: rgba(255, 255, 255, 0.94);
      border: 1px solid rgba(0, 0, 0, 0.18);
      border-radius: 5px;
      box-shadow: 0 1px 5px rgba(0, 0, 0, 0.25);
      color: #222;
      line-height: 1.35;
      padding: 10px 12px;
    }}
    .map-title {{ max-width: 360px; }}
    .map-title h1 {{ font-size: 16px; margin: 0 0 5px; }}
    .map-title p {{ font-size: 12px; margin: 2px 0; }}
    .map-legend {{ min-width: 135px; }}
    .map-legend h2 {{ font-size: 13px; margin: 0 0 8px; }}
    .legend-row {{ align-items: center; display: flex; gap: 7px; margin: 5px 0; }}
    .legend-circle {{
      background: #1976a8;
      border: 1px solid #0d3d57;
      border-radius: 50%;
      display: inline-block;
      flex: 0 0 auto;
      opacity: 0.72;
    }}
    .legend-small {{ height: 6px; width: 6px; }}
    .legend-medium {{ height: 16px; width: 16px; }}
    .legend-large {{ height: 28px; width: 28px; }}
    .school-marker-wrapper {{
      background: transparent;
      border: 0;
    }}
    .school-marker {{
      background: #1976a8;
      border: 1px solid #0d3d57;
      border-radius: 50%;
      box-sizing: border-box;
      display: block;
      opacity: 0.82;
    }}
    .leaflet-popup-content {{ margin: 12px 14px; }}
    .popup-title {{ font-weight: 700; margin-bottom: 5px; }}
    .popup-table td {{ padding: 2px 8px 2px 0; vertical-align: top; }}
    .popup-table td:first-child {{ color: #555; }}
  </style>
</head>
<body>
  <div id="map"></div>
  <script src="https://unpkg.com/leaflet@{LEAFLET_VERSION}/dist/leaflet.js"
          crossorigin=""></script>
  <script src="https://cdn.jsdelivr.net/npm/leaflet.markercluster@{MARKERCLUSTER_VERSION}/dist/leaflet.markercluster.js"></script>
  <script>
    const SCHOOLS = {data};
    const SUMMARY = {summary};
    const MAX_M_MIN = SUMMARY.m_min_max;
    const MIN_RADIUS = {MIN_RADIUS_PX};
    const MAX_RADIUS = {MAX_RADIUS_PX};

    // Use screen pixels, not metres: zooming never makes a marker physically
    // enormous or imperceptibly small.
    function radiusFor(value) {{
      if (!MAX_M_MIN) return MIN_RADIUS;
      return MIN_RADIUS + (MAX_RADIUS - MIN_RADIUS) * Math.sqrt(value / MAX_M_MIN);
    }}

    function iconFor(school) {{
      const radius = radiusFor(school.m_min);
      const diameter = radius * 2;
      return L.divIcon({{
        className: "school-marker-wrapper",
        html: `<span class="school-marker" style="width:${{diameter}}px;height:${{diameter}}px"></span>`,
        iconSize: [diameter, diameter],
        iconAnchor: [radius, radius],
        popupAnchor: [0, -radius]
      }});
    }}

    function escapeHtml(value) {{
      return String(value ?? "").replace(/[&<>"']/g, character => ({{
        "&": "&amp;", "<": "&lt;", ">": "&gt;", "\\\"": "&quot;", "'": "&#039;"
      }}[character]));
    }}

    function popupFor(school) {{
      const address = school.formatted_address ||
        [school.comune, school.provincia, school.regione].filter(Boolean).join(", ");
      return `
        <div class="popup-title">${{escapeHtml(school.name || school.code)}}</div>
        <table class="popup-table">
          <tr><td>Codice</td><td>${{escapeHtml(school.code)}}</td></tr>
          <tr><td>Comune</td><td>${{escapeHtml(school.comune)}}</td></tr>
          <tr><td>Indirizzo geocodificato</td><td>${{escapeHtml(address)}}</td></tr>
          <tr><td><code>m_min_sopra_30</code></td><td><strong>${{school.m_min}}</strong></td></tr>
          <tr><td>Unità analizzate</td><td>${{school.unita_totali}}</td></tr>
          <tr><td>Unità sopra il 30%</td><td>${{school.unita_sopra_30}}</td></tr>
          <tr><td>Granularità</td><td>${{escapeHtml(school.granularita)}}</td></tr>
        </table>`;
    }}

    const map = L.map("map", {{
      preferCanvas: true,
      minZoom: 5,
      maxZoom: 18,
      zoomControl: true
    }});
    L.tileLayer("{TILE_URL}", {{
      maxZoom: 19,
      attribution: "{TILE_ATTRIBUTION}"
    }}).addTo(map);

    const markers = L.markerClusterGroup({{
      chunkedLoading: true,
      chunkInterval: 100,
      chunkDelay: 20,
      maxClusterRadius: 45,
      showCoverageOnHover: false,
      zoomToBoundsOnClick: true,
      spiderfyOnMaxZoom: true,
      disableClusteringAtZoom: 13
    }});
    const schoolMarkers = [];
    for (const school of SCHOOLS) {{
      const marker = L.marker([school.lat, school.lon], {{ icon: iconFor(school) }});
      marker.bindPopup(popupFor(school), {{ maxWidth: 420 }});
      schoolMarkers.push(marker);
    }}
    const dataBounds = SCHOOLS.length
      ? L.latLngBounds(SCHOOLS.map(school => [school.lat, school.lon]))
      : null;
    markers.addLayers(schoolMarkers);
    markers.addTo(map);

    if (dataBounds) {{
      map.fitBounds(dataBounds, {{ padding: [28, 28], maxZoom: 8 }});
    }} else {{
      map.setView([42.5, 12.5], 6);
    }}

    const title = L.control({{ position: "topleft" }});
    title.onAdd = function() {{
      const div = L.DomUtil.create("div", "map-title");
      div.innerHTML = `<h1>Scuole MIM 2024/25</h1>
        <p>Plessi analizzati: ${{SUMMARY.plessi_plottati.toLocaleString("it-IT")}} / ${{SUMMARY.plessi_target.toLocaleString("it-IT")}}</p>
        <p>Visualizzati solo i plessi con <code>m_min_sopra_30 &gt; 0</code> (esclusi: ${{SUMMARY.esclusi_m_min_zero.toLocaleString("it-IT")}}).</p>
        <p>I cerchi più grandi indicano valori maggiori di <code>m_min_sopra_30</code>.</p>`;
      L.DomEvent.disableClickPropagation(div);
      return div;
    }};
    title.addTo(map);

    const legend = L.control({{ position: "bottomright" }});
    legend.onAdd = function() {{
      const div = L.DomUtil.create("div", "map-legend");
      const middle = Math.round(MAX_M_MIN / 2);
      div.innerHTML = `<h2>m_min_sopra_30</h2>
        <div class="legend-row"><span class="legend-circle legend-small"></span><span>0</span></div>
        <div class="legend-row"><span class="legend-circle legend-medium"></span><span>${{middle}}</span></div>
        <div class="legend-row"><span class="legend-circle legend-large"></span><span>${{MAX_M_MIN}}</span></div>`;
      return div;
    }};
    legend.addTo(map);
  </script>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--aggregates",
        type=Path,
        default=DEFAULT_AGGREGATES,
        help=f"CSV degli aggregati (default: {DEFAULT_AGGREGATES})",
    )
    parser.add_argument(
        "--geocoding",
        type=Path,
        default=DEFAULT_GEOCODING,
        help=f"CSV del geocoding (default: {DEFAULT_GEOCODING})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"HTML di output (default: {DEFAULT_OUTPUT})",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    target = load_target_rows(args.aggregates)
    target_count = len(target)
    target_nonzero: dict[str, dict[str, str]] = {}
    excluded_zero = 0
    for code, aggregate in target.items():
        m_min = as_nonnegative_int(
            aggregate["m_min_sopra_30"], "m_min_sopra_30", code, args.aggregates
        )
        if m_min == 0:
            excluded_zero += 1
        else:
            target_nonzero[code] = aggregate

    if not target_nonzero:
        raise ValueError("Nessun plesso ha m_min_sopra_30 > 0")

    geocoding = load_geocoding_rows(args.geocoding)
    rows, missing_geocoding, missing_coordinates = join_rows(
        target_nonzero, geocoding, args.geocoding, args.aggregates
    )
    html = build_html(
        rows,
        target_count,
        excluded_zero,
        missing_geocoding,
        missing_coordinates,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html, encoding="utf-8")
    print(
        f"Mappa scritta in {args.output}: {len(rows)}/{target_count} plessi "
        f"visualizzati; esclusi {excluded_zero} con m_min_sopra_30=0. "
        f"Valore massimo m_min_sopra_30: "
        f"{max(int(row['m_min']) for row in rows)}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
