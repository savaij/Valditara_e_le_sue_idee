"""Guardrails for the published 2024/25 scenario and its two heatmaps."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "src" / "analysis_big_cities"))

import plot_heatmaps  # noqa: E402
import simulate_realloc  # noqa: E402


class CurrentScenarioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.units = plot_heatmaps.read_csv(ROOT / "data_processed" / "unita_202425.csv")
        cls.geocoding = plot_heatmaps.read_csv(ROOT / "data_processed" / "geocoding_scuole_202425.csv")
        cls.summary = json.loads((ROOT / "results" / "summary_202425.json").read_text())
        cls.simulation = json.loads(
            (ROOT / "results" / "simulazione_riepilogo_202425_seed42.json").read_text()
        )

    def test_all_years_map_matches_summary(self) -> None:
        origins, n_units = plot_heatmaps.aggregate_origins(self.units, "tutti_anni")
        points = plot_heatmaps.add_coordinates(origins, self.geocoding)
        self.assertEqual(n_units, self.summary["units_above_30"])
        self.assertEqual(sum(point["value"] for point in points), self.summary["students_non_nati_in_Italia_in_units_above_30"])
        self.assertTrue(all(int(row["alunni_totali"]) >= 10 for row in self.units))

    def test_first_year_map_matches_simulation(self) -> None:
        origins, n_units = plot_heatmaps.aggregate_origins(self.units, "prime")
        points = plot_heatmaps.add_coordinates(origins, self.geocoding)
        unallocated = plot_heatmaps.add_unallocated(
            points,
            plot_heatmaps.read_csv(ROOT / "results" / "simulazione_non_riallocabili_202425_seed42.csv"),
            self.simulation,
        )
        self.assertEqual(n_units, self.simulation["unita_sopra_30_totali"])
        self.assertEqual(sum(point["value"] for point in points), self.simulation["studenti_da_riallocare_totale"])
        self.assertEqual(unallocated, 72)
        self.assertEqual(self.simulation["max_km_applicato"], 5.0)
        self.assertEqual(self.simulation["max_limit_per_class"], 30)
        self.assertEqual(
            self.simulation["studenti_riallocati_totale"] + self.simulation["studenti_non_riallocati_totale"],
            self.simulation["studenti_da_riallocare_totale"],
        )

    def test_single_run_defaults_match_published_scenario(self) -> None:
        original_argv = sys.argv
        try:
            sys.argv = ["simulate_realloc.py"]
            args = simulate_realloc.parse_args()
        finally:
            sys.argv = original_argv
        self.assertEqual(args.max_km, 5.0)
        self.assertTrue(args.consenti_cambio_tipologia_scuola)
        self.assertEqual(simulate_realloc.MAX_LIMIT_PER_CLASS, 30)

    def test_map_rejects_small_units(self) -> None:
        row = dict(self.units[0])
        row["alunni_totali"] = "9"
        with self.assertRaisesRegex(ValueError, "meno di 10"):
            plot_heatmaps.aggregate_origins([row], "tutti_anni")

    def test_map_uses_numbered_markers_and_unallocated_filter(self) -> None:
        origins, _ = plot_heatmaps.aggregate_origins(self.units, "prime")
        points = plot_heatmaps.add_coordinates(origins, self.geocoding)
        plot_heatmaps.add_unallocated(
            points,
            plot_heatmaps.read_csv(ROOT / "results" / "simulazione_non_riallocabili_202425_seed42.csv"),
            self.simulation,
        )
        html = plot_heatmaps.build_html(points, "Studenti da riallocare nelle prime", "Entro 5 km.", "prime")
        self.assertIn("markerFor(p,p.value,label).addTo(allLayer)", html)
        self.assertIn("markerFor(p,p.unallocated,'Non riallocabili entro 5 km').addTo(unallocatedLayer)", html)
        self.assertIn("map.removeLayer(allLayer)", html)
        self.assertIn("map.addLayer(allLayer)", html)
        self.assertIn("L.markerClusterGroup", html)
        self.assertIn("cluster.getAllChildMarkers().reduce", html)
        self.assertIn("count<10?40:count<50?46:52", html)
        self.assertIn("unallocatedTotal=72", html)
        self.assertNotIn("heatLayer", html)
        self.assertNotIn("Geocodifica:", html)

    def test_current_municipality_result(self) -> None:
        rows = plot_heatmaps.read_csv(ROOT / "results" / "comuni_cambio_comune_202425.csv")
        first_year_municipalities = {
            row["codice_comune"] for row in self.units if row["anno_corso"] == "1"
        }
        self.assertEqual(len(rows), 27)
        self.assertEqual(len({row["codice_comune"] for row in rows}), 23)
        self.assertEqual(len(first_year_municipalities), 5272)
        self.assertEqual(sum(float(row["studenti_senza_posto"]) for row in rows), 107)


if __name__ == "__main__":
    unittest.main()
