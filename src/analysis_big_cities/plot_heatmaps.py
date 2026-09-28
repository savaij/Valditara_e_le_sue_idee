#!/usr/bin/env python3
"""Heatmap delle classi sopra 30 studenti per zona urbanistica.

Per ciascuna delle grandi città elencate in ``CITY_NAMES`` il modulo:

1. seleziona da ``aggregati_202425.csv`` le righe con
   ``livello_aggregazione == "plesso"`` e ``tipo_gestione == "tutte"``
   (stesso sottoinsieme usato da ``plot_schools.py``);
2. le unisce a ``geocoding_scuole_202425.csv`` su ``codice_scuola`` per
   ottenere le coordinate di ciascun plesso;
3. assegna ogni plesso alla zona urbanistica che lo contiene tramite join
   spaziale con lo shapefile di livello 2 (``ASC_Liv_2_2021.shp``);
4. somma, per ciascuna zona, il valore di ``classi_sopra_trenta`` dei plessi
   con ``m_min_sopra_30 > 0`` — un plesso non pesa 1, ma quanto il suo numero
   di classi sopra i 30 studenti;
5. disegna una heatmap (coropleta) statica per città e la salva come PNG in
   ``results/results_big_cities``, e una versione interattiva in HTML in cui
   ogni zona mostra al passaggio del mouse il numero di classi sopra il 30%
   e il numero minimo di studenti da rilocare stimato da ``analyze.py``
   (``m_min_sopra_30``, basato sugli alunni non nati in Italia, non sulla
   sola cittadinanza).

Le zone senza alcuna classe sopra soglia restano nella mappa con il colore
più chiaro della scala (valore 0), non vengono rimosse.

Uso dalla root del progetto::

    python src/analysis_big_cities/plot_heatmaps.py

Percorsi opzionali per test o run alternativi::

    python src/analysis_big_cities/plot_heatmaps.py --aggregates ... --geocoding ... \\
        --shapefile ... --output-dir ...
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd
import plotly.graph_objects as go
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.ticker import MaxNLocator

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AGGREGATES = ROOT / "results" / "aggregati_202425.csv"
DEFAULT_GEOCODING = ROOT / "data_processed" / "geocoding_scuole_202425.csv"
DEFAULT_SHAPEFILE = ROOT / "data_geo" / "ASC_21" / "ASC_Liv_2_2021.shp"
DEFAULT_OUTPUT_DIR = ROOT / "results" / "results_big_cities"

# Mappa PRO_COM (codice ISTAT comune) -> nome città, per le città analizzate.
CITY_NAMES: dict[int, str] = {
    58091: "Roma",
    10025: "Genova",
    100005: "Prato",
    82053: "Palermo",
    37006: "Bologna",
    1272: "Torino",
    15146: "Milano",
    63049: "Napoli",
}

# Rampa sequenziale blu (dal chiaro allo scuro) per la codifica di grandezza.
SEQUENTIAL_BLUE_STEPS = [
    "#cde2fb",
    "#b7d3f6",
    "#9ec5f4",
    "#86b6ef",
    "#6da7ec",
    "#5598e7",
    "#3987e5",
    "#2a78d6",
    "#256abf",
    "#1c5cab",
    "#184f95",
    "#104281",
    "#0d366b",
]

AGGREGATE_FIELDS = {
    "livello_aggregazione",
    "tipo_gestione",
    "codice_scuola",
    "comune",
    "m_min_sopra_30",
    "classi_sopra_trenta",
}
GEOCODING_FIELDS = {"codice_scuola", "lat", "lon"}


def sequential_blue_cmap() -> LinearSegmentedColormap:
    return LinearSegmentedColormap.from_list("blue_seq", SEQUENTIAL_BLUE_STEPS)


def require_fields(path: Path, df: pd.DataFrame, fields: set[str]) -> None:
    missing = sorted(fields - set(df.columns))
    if missing:
        raise ValueError(f"{path}: colonne mancanti: {', '.join(missing)}")


def load_school_points(aggregates_path: Path, geocoding_path: Path) -> gpd.GeoDataFrame:
    """Carica i plessi (aggregato tutte) con coordinate, come GeoDataFrame in EPSG:4326."""

    aggregates = pd.read_csv(aggregates_path, dtype=str)
    require_fields(aggregates_path, aggregates, AGGREGATE_FIELDS)
    target = aggregates[
        (aggregates["livello_aggregazione"].str.strip() == "plesso")
        & (aggregates["tipo_gestione"].str.strip() == "tutte")
        & aggregates["codice_scuola"].str.strip().astype(bool)
    ].copy()
    if target.empty:
        raise ValueError(
            f"{aggregates_path}: nessuna riga con livello_aggregazione=plesso "
            "e tipo_gestione=tutte"
        )
    target["codice_scuola"] = target["codice_scuola"].str.strip()
    duplicates = target["codice_scuola"][target["codice_scuola"].duplicated()].unique()
    if len(duplicates):
        raise ValueError(
            f"{aggregates_path}: codici scuola duplicati nel sottoinsieme target: "
            f"{', '.join(duplicates[:10])}"
        )
    target["m_min_sopra_30"] = pd.to_numeric(
        target["m_min_sopra_30"], errors="raise"
    ).astype(int)
    if (target["m_min_sopra_30"] < 0).any():
        raise ValueError(f"{aggregates_path}: valori negativi in m_min_sopra_30")
    target["classi_sopra_trenta"] = pd.to_numeric(
        target["classi_sopra_trenta"], errors="raise"
    ).astype(int)
    if (target["classi_sopra_trenta"] < 0).any():
        raise ValueError(f"{aggregates_path}: valori negativi in classi_sopra_trenta")

    geocoding = pd.read_csv(geocoding_path, dtype=str)
    require_fields(geocoding_path, geocoding, GEOCODING_FIELDS)
    geocoding = geocoding.copy()
    geocoding["codice_scuola"] = geocoding["codice_scuola"].str.strip()
    if geocoding["codice_scuola"].duplicated().any():
        dup = geocoding.loc[
            geocoding["codice_scuola"].duplicated(), "codice_scuola"
        ].unique()
        raise ValueError(f"{geocoding_path}: codice_scuola duplicato: {', '.join(dup[:10])}")

    merged = target.merge(
        geocoding[["codice_scuola", "lat", "lon"]], on="codice_scuola", how="left"
    )
    missing_geocoding = merged["lat"].isna() | merged["lon"].isna()
    n_missing = int(missing_geocoding.sum())
    if n_missing:
        print(
            f"ATTENZIONE: {n_missing} plessi senza coordinate di geocoding "
            "(esclusi dall'analisi)",
            file=sys.stderr,
        )
    merged = merged.loc[~missing_geocoding].copy()
    merged["lat"] = merged["lat"].astype(float)
    merged["lon"] = merged["lon"].astype(float)

    points = gpd.GeoDataFrame(
        merged[["codice_scuola", "comune", "m_min_sopra_30", "classi_sopra_trenta"]],
        geometry=gpd.points_from_xy(merged["lon"], merged["lat"]),
        crs="EPSG:4326",
    )
    return points


def assign_zones(points: gpd.GeoDataFrame, zones: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Associa ogni plesso alla zona urbanistica che lo contiene."""

    points_projected = points.to_crs(zones.crs)
    joined = gpd.sjoin(
        points_projected,
        zones[["PRO_COM", "COD_ASC2", "geometry"]],
        how="left",
        predicate="within",
    )
    n_unmatched = int(joined["COD_ASC2"].isna().sum())
    if n_unmatched:
        print(
            f"ATTENZIONE: {n_unmatched} plessi non ricadono in nessuna zona "
            "urbanistica dello shapefile",
            file=sys.stderr,
        )
    return joined.dropna(subset=["COD_ASC2"])


def zone_metrics(joined: gpd.GeoDataFrame, city_code: int) -> pd.DataFrame:
    """Somma, per zona (COD_ASC2), le metriche dei plessi con m_min_sopra_30 > 0
    nella città data: ``classi_sopra_trenta`` (un plesso pesa quanto il suo
    numero di classi sopra i 30 studenti, non 1) e ``m_min_sopra_30`` (numero
    minimo di studenti da rilocare per rientrare sotto il 30%, stimato su chi
    non è nato in Italia)."""

    city_schools = joined[joined["PRO_COM"] == city_code]
    above_threshold = city_schools[city_schools["m_min_sopra_30"] > 0]
    return above_threshold.groupby("COD_ASC2")[["classi_sopra_trenta", "m_min_sopra_30"]].sum()


def plot_city_heatmap(
    zones_city: gpd.GeoDataFrame,
    city_name: str,
    n_plessi_sopra_30: int,
    n_plessi_totali: int,
    cmap: LinearSegmentedColormap,
    output_path: Path,
) -> None:
    max_count = int(zones_city["classi_sopra_trenta"].max())
    norm = Normalize(vmin=0, vmax=max(max_count, 1))

    fig, ax = plt.subplots(figsize=(10, 10))
    zones_city.plot(
        column="classi_sopra_trenta",
        cmap=cmap,
        norm=norm,
        edgecolor="white",
        linewidth=0.4,
        ax=ax,
    )
    ax.set_axis_off()
    ax.set_aspect("equal")
    ax.set_title(
        f"{city_name} — classi sopra 30 studenti per zona urbanistica",
        fontsize=14,
    )
    total_classi = int(zones_city["classi_sopra_trenta"].sum())
    ax.text(
        0.5,
        -0.02,
        f"Classi sopra 30 studenti: {total_classi} — plessi sopra soglia: "
        f"{n_plessi_sopra_30} / {n_plessi_totali} — zone urbanistiche: {len(zones_city)}",
        transform=ax.transAxes,
        ha="center",
        va="top",
        fontsize=9,
        color="#52514e",
    )

    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, shrink=0.7)
    cbar.set_label("Classi sopra 30 studenti")
    cbar.locator = MaxNLocator(integer=True)
    cbar.update_ticks()

    fig.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


ZOOM_BREAKS = [
    (360.0, 1), (180.0, 2), (90.0, 3), (45.0, 4), (22.5, 5), (11.25, 6),
    (5.625, 7), (2.813, 8), (1.406, 9), (0.703, 10), (0.352, 11),
    (0.176, 12), (0.088, 13), (0.044, 14), (0.022, 15), (0.011, 16),
]


def center_and_zoom(bounds: tuple[float, float, float, float]) -> tuple[dict[str, float], int]:
    """Centro e livello di zoom approssimati per inquadrare un bounding box (lon/lat)."""

    minx, miny, maxx, maxy = bounds
    center = {"lat": (miny + maxy) / 2, "lon": (minx + maxx) / 2}
    max_range = max(maxx - minx, maxy - miny)
    zoom = 16
    for threshold, level in ZOOM_BREAKS:
        if max_range > threshold:
            zoom = level
            break
    return center, zoom


def plot_city_interactive(
    zones_city: gpd.GeoDataFrame,
    city_name: str,
    output_path: Path,
) -> None:
    """Salva una heatmap interattiva in HTML con tooltip per ogni zona."""

    zones_4326 = zones_city.to_crs("EPSG:4326")
    geojson = json.loads(zones_4326.to_json())
    max_count = int(zones_4326["classi_sopra_trenta"].max())

    trace = go.Choroplethmap(
        geojson=geojson,
        locations=zones_4326["COD_ASC2"],
        z=zones_4326["classi_sopra_trenta"],
        featureidkey="properties.COD_ASC2",
        colorscale=[
            [i / (len(SEQUENTIAL_BLUE_STEPS) - 1), color]
            for i, color in enumerate(SEQUENTIAL_BLUE_STEPS)
        ],
        zmin=0,
        zmax=max(max_count, 1),
        marker_line_width=0.6,
        marker_line_color="white",
        marker_opacity=0.85,
        customdata=zones_4326[["DEN_ASC2", "m_min_sopra_30"]],
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Numero di classi con oltre il trenta percento di studenti: %{z}<br>"
            "Numero minimo di studenti da rilocare per ottenere il 30%: "
            "%{customdata[1]}"
            "<extra></extra>"
        ),
        colorbar=dict(title="Classi sopra 30 studenti"),
    )

    center, zoom = center_and_zoom(tuple(zones_4326.total_bounds))
    fig = go.Figure(trace)
    fig.update_layout(
        map_style="carto-positron",
        map_center=center,
        map_zoom=zoom,
        title=f"{city_name} — classi sopra 30 studenti per zona urbanistica",
        margin=dict(l=0, r=0, t=40, b=0),
    )
    fig.write_html(output_path, include_plotlyjs="cdn")


def slugify(name: str) -> str:
    return name.strip().lower().replace(" ", "_")


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
        "--shapefile",
        type=Path,
        default=DEFAULT_SHAPEFILE,
        help=f"Shapefile delle zone urbanistiche (default: {DEFAULT_SHAPEFILE})",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Cartella di output per le heatmap (default: {DEFAULT_OUTPUT_DIR})",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    points = load_school_points(args.aggregates, args.geocoding)
    zones = gpd.read_file(args.shapefile)
    require_fields(args.shapefile, zones, {"PRO_COM", "COD_ASC2", "DEN_ASC2", "geometry"})
    joined = assign_zones(points, zones)

    cmap = sequential_blue_cmap()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    for city_code, city_name in CITY_NAMES.items():
        zones_city = zones[zones["PRO_COM"] == city_code].copy()
        if zones_city.empty:
            print(
                f"ATTENZIONE: nessuna zona urbanistica trovata per {city_name} "
                f"(PRO_COM={city_code}), città saltata",
                file=sys.stderr,
            )
            continue

        zone_sums = zone_metrics(joined, city_code)
        zones_city["classi_sopra_trenta"] = (
            zones_city["COD_ASC2"].map(zone_sums["classi_sopra_trenta"]).fillna(0).astype(int)
        )
        zones_city["m_min_sopra_30"] = (
            zones_city["COD_ASC2"].map(zone_sums["m_min_sopra_30"]).fillna(0).astype(int)
        )

        city_schools = joined[joined["PRO_COM"] == city_code]
        n_plessi_sopra_30 = int((city_schools["m_min_sopra_30"] > 0).sum())
        n_plessi_totali = int(len(city_schools))
        total_classi = int(zones_city["classi_sopra_trenta"].sum())

        png_path = args.output_dir / f"heatmap_{slugify(city_name)}.png"
        plot_city_heatmap(
            zones_city,
            city_name,
            n_plessi_sopra_30,
            n_plessi_totali,
            cmap,
            png_path,
        )
        html_path = args.output_dir / f"heatmap_{slugify(city_name)}.html"
        plot_city_interactive(zones_city, city_name, html_path)
        print(
            f"{city_name}: {total_classi} classi sopra 30 studenti "
            f"({n_plessi_sopra_30}/{n_plessi_totali} plessi con m_min_sopra_30>0) "
            f"su {len(zones_city)} zone -> {png_path}, {html_path}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
