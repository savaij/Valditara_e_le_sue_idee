#!/usr/bin/env python3
"""Genera due mappe interattive a punti per lo scenario MIM 2024/25.

La prima mostra gli studenti stimati nel numeratore dei gruppi sopra il 30%
in tutti gli anni; la seconda mostra m_min nelle sole prime e consente di
evidenziare gli studenti senza destinazione nella simulazione entro 5 km.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UNITS = ROOT / "data_processed" / "unita_202425.csv"
GEOCODING = ROOT / "data_processed" / "geocoding_scuole_202425.csv"
SIMULATION = ROOT / "results" / "simulazione_riepilogo_202425_seed42.json"
UNALLOCATED = ROOT / "results" / "simulazione_non_riallocabili_202425_seed42.csv"
RESULTS = ROOT / "results"

MAPS = (
    (
        "tutti_anni",
        "mappa_studenti_sopra_30_tutti_anni_202425.html",
        "Studenti nei gruppi sopra il 30%",
        "Tutti gli anni di corso. Sono gli studenti stimati nel numeratore dei gruppi sopra soglia, non quelli da spostare.",
    ),
    (
        "prime",
        "mappa_studenti_da_riallocare_prime_202425.html",
        "Studenti da riallocare nelle prime",
        "Studenti stimati da riallocare nelle prime classi. Le destinazioni sono cercate entro 5 km tra plessi.",
    ),
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def nonnegative_int(value: str, field: str, code: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise ValueError(f"{field} non intero per {code}: {value!r}") from exc
    if number < 0:
        raise ValueError(f"{field} negativo per {code}: {number}")
    return number


def aggregate_origins(units: list[dict[str, str]], mode: str) -> tuple[dict[str, dict[str, object]], int]:
    by_school: dict[str, dict[str, object]] = {}
    n_units = 0
    for row in units:
        code = row["codice_scuola"].strip()
        if nonnegative_int(row["alunni_totali"], "alunni_totali", code) < 10:
            raise ValueError(f"{code}: il file include un gruppo con meno di 10 studenti")
        if row["sopra_30"] != "1" or (mode == "prime" and row["anno_corso"] != "1"):
            continue
        n_units += 1
        field = "m_min" if mode == "prime" else "alunni_non_nati_in_Italia"
        value = nonnegative_int(row[field], field, code) if row[field] else 0
        if value == 0:
            continue
        if code not in by_school:
            by_school[code] = {
                "code": code, "name": row["denominazione_scuola"],
                "comune": row["comune"], "provincia": row["provincia"],
                "value": 0,
            }
        by_school[code]["value"] += value  # type: ignore[operator]
    return by_school, n_units


def add_coordinates(
    origins: dict[str, dict[str, object]], geocoding: list[dict[str, str]]
) -> list[dict[str, object]]:
    by_code: dict[str, dict[str, str]] = {}
    for row in geocoding:
        code = row["codice_scuola"].strip()
        if code in by_code:
            raise ValueError(f"Codice scuola duplicato nel geocoding: {code}")
        by_code[code] = row
    points: list[dict[str, object]] = []
    for code, origin in origins.items():
        geo = by_code.get(code)
        if geo is None or not geo["lat"] or not geo["lon"]:
            raise ValueError(f"Coordinate mancanti per un'origine sopra soglia: {code}")
        lat, lon = float(geo["lat"]), float(geo["lon"])
        if not math.isfinite(lat) or not math.isfinite(lon) or not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            raise ValueError(f"Coordinate non valide per {code}: {lat}, {lon}")
        points.append({**origin, "lat": lat, "lon": lon})
    return sorted(points, key=lambda row: str(row["code"]))


def add_unallocated(
    points: list[dict[str, object]], rows: list[dict[str, str]], summary: dict[str, object]
) -> int:
    if summary["max_km_applicato"] != 5.0 or summary["max_limit_per_class"] != 30:
        raise ValueError("Il riepilogo della simulazione non usa lo scenario 5 km / 30 alunni")
    if summary["studenti_da_riallocare_totale"] != sum(int(point["value"]) for point in points):
        raise ValueError("La domanda della mappa non coincide con la simulazione")
    by_code = {str(point["code"]): point for point in points}
    for point in points:
        point["unallocated"] = 0
    for row in rows:
        code = row["codice_scuola_origine"].strip()
        if row["anno_corso"] != "1" or code not in by_code:
            raise ValueError(f"Origine non riconosciuta nel file dei non riallocabili: {code}")
        by_code[code]["unallocated"] += nonnegative_int(
            row["n_studenti_non_riallocati"], "n_studenti_non_riallocati", code
        )  # type: ignore[operator]
    total = sum(int(point["unallocated"]) for point in points)
    if total != summary["studenti_non_riallocati_totale"]:
        raise ValueError("Il totale dei non riallocabili non coincide con la simulazione")
    if any(int(point["unallocated"]) > int(point["value"]) for point in points):
        raise ValueError("Una scuola ha più studenti non riallocabili che studenti da riallocare")
    return total


def build_html(points: list[dict[str, object]], title: str, note: str, mode: str) -> str:
    if not points:
        raise ValueError("Nessun plesso da rappresentare")
    total = sum(int(point["value"]) for point in points)
    unallocated = sum(int(point.get("unallocated", 0)) for point in points)
    data = json.dumps(points, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    heading = json.dumps(title, ensure_ascii=False).replace("</", "<\\/")
    explanation = json.dumps(note, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css">
<style>
html,body,#map{{height:100%;margin:0}} body{{font-family:system-ui,sans-serif}}
.panel{{background:#fff;border:1px solid #bbb;border-radius:6px;box-shadow:0 1px 6px #777;padding:11px;max-width:320px;line-height:1.4}}
.panel h1{{font-size:16px;margin:0 0 6px}} .panel p{{font-size:12px;margin:5px 0}}
.legend-dot{{display:inline-block;width:16px;height:16px;background:#245b94;border:2px solid #fff;border-radius:50%;box-shadow:0 0 0 1px #163c64;vertical-align:middle}}
.student-marker{{width:38px;height:38px;box-sizing:border-box;border-radius:50%;background:#245b94;border:2px solid #fff;box-shadow:0 1px 5px #26384b;color:#fff;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:800;line-height:1}}
.cluster-marker{{box-sizing:border-box;border-radius:50%;background:#245b94;border:3px solid #fff;box-shadow:0 1px 6px #26384b;color:#fff;display:flex;align-items:center;justify-content:center;font-weight:800;line-height:1}}
</style></head><body><div id="map"></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
<script>
const points={data}, title={heading}, note={explanation};
const total={total}, unallocatedTotal={unallocated}, firstYears={str(mode == 'prime').lower()};
const map=L.map('map').setView([42.5,12.5],6);
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',{{maxZoom:18,attribution:'&copy; OpenStreetMap contributors'}}).addTo(map);
function esc(s){{return String(s??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));}}
function markerFor(p,count,label){{
 const icon=L.divIcon({{className:'',html:'<span class="student-marker">'+count+'</span>',iconSize:[38,38],iconAnchor:[19,19],popupAnchor:[0,-19]}});
 const marker=L.marker([p.lat,p.lon],{{icon,studentCount:count}});
 marker.bindPopup('<strong>'+esc(p.name)+'</strong><br>'+esc(p.comune)+' ('+esc(p.provincia)+')<br>'+label+': <strong>'+count+'</strong><br>Codice: '+esc(p.code));
 marker.bindTooltip(count+' '+(count===1?'studente':'studenti'));
 return marker;
}}
function clusterDiameter(count){{return count<10?40:count<50?46:52;}}
function clusterIcon(cluster){{
 const count=cluster.getAllChildMarkers().reduce((sum,marker)=>sum+marker.options.studentCount,0);
 const diameter=clusterDiameter(count), radius=diameter/2;
 return L.divIcon({{className:'',html:'<span class="cluster-marker" style="width:'+diameter+'px;height:'+diameter+'px;font-size:14px">'+count+'</span>',iconSize:[diameter,diameter],iconAnchor:[radius,radius]}});
}}
function clusterLayer(){{return L.markerClusterGroup({{iconCreateFunction:clusterIcon,maxClusterRadius:75,showCoverageOnHover:false,spiderfyOnMaxZoom:true,disableClusteringAtZoom:13}});}}
const allLayer=clusterLayer().addTo(map);
const unallocatedLayer=clusterLayer();
for(const p of points){{
 const label=firstYears?'Da riallocare':'Studenti nei gruppi sopra soglia';
 markerFor(p,p.value,label).addTo(allLayer);
 if(firstYears && p.unallocated>0){{
   markerFor(p,p.unallocated,'Non riallocabili entro 5 km').addTo(unallocatedLayer);
 }}
}}
if(firstYears){{
 L.control.layers(null,{{['Solo non riallocabili entro 5 km ('+unallocatedTotal+')']:unallocatedLayer}},{{collapsed:false}}).addTo(map);
 map.on('overlayadd',event=>{{if(event.layer===unallocatedLayer)map.removeLayer(allLayer);}});
 map.on('overlayremove',event=>{{if(event.layer===unallocatedLayer)map.addLayer(allLayer);}});
}}
map.fitBounds(L.latLngBounds(points.map(p=>[p.lat,p.lon])),{{padding:[30,30],maxZoom:9}});
const panel=L.control({{position:'topleft'}});
panel.onAdd=()=>{{const el=L.DomUtil.create('div','panel');el.innerHTML='<h1>'+esc(title)+'</h1><p>'+esc(note)+'</p><p><span class="legend-dot"></span> '+total.toLocaleString('it-IT')+' studenti stimati. Allontanandosi, i cerchi vicini si uniscono: il numero è la somma. I cerchi più grandi restano compatti.</p>';L.DomEvent.disableClickPropagation(el);return el;}};
panel.addTo(map);
</script></body></html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--units", type=Path, default=UNITS)
    parser.add_argument("--geocoding", type=Path, default=GEOCODING)
    parser.add_argument("--simulation", type=Path, default=SIMULATION)
    parser.add_argument("--unallocated", type=Path, default=UNALLOCATED)
    parser.add_argument("--output-dir", type=Path, default=RESULTS)
    args = parser.parse_args()
    units = read_csv(args.units)
    geocoding = read_csv(args.geocoding)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for mode, filename, title, note in MAPS:
        origins, n_units = aggregate_origins(units, mode)
        points = add_coordinates(origins, geocoding)
        if mode == "prime":
            summary = json.loads(args.simulation.read_text(encoding="utf-8"))
            unallocated = add_unallocated(points, read_csv(args.unallocated), summary)
        else:
            unallocated = 0
        output = args.output_dir / filename
        output.write_text(build_html(points, title, note, mode), encoding="utf-8")
        print(f"{output}: {sum(int(point['value']) for point in points)} studenti, {n_units} gruppi, {len(points)} plessi, {unallocated} non riallocabili")


if __name__ == "__main__":
    main()
