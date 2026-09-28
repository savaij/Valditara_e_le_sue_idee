#!/usr/bin/env python3
"""Conta i comuni con un deficit di posti per la riallocazione nello scenario modellato.

Per ogni comune (anno_corso == 1) e per ogni combinazione (ordine_scuola,
tipo_scuola_anagrafe) si confronta il numero minimo di studenti da spostare
(`m_min`) con la disponibilità effettiva delle unità dello stesso comune, cioè
il minimo tra i posti fisici liberi e gli alunni non nati in Italia che
l'unità può ancora accogliere restando sotto il 30% (stessa proxy usata da
analyze.py e simulate_realloc.py per il criterio del 30%). Se gli studenti da
spostare superano la disponibilità, il gruppo ha un deficit di posti interni
al comune, date le ipotesi del modello. Non si verifica la disponibilità
fuori comune.

Con `--consenti-cambio-tipo-scuola` il vincolo su `tipo_scuola_anagrafe` viene
ignorato: il confronto si fa solo per (comune, ordine_scuola).
"""

import argparse
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data_processed" / "unita_202425.csv"
RESULTS = ROOT / "results"

ALUNNI_PER_CLASSE = 30
SOGLIA = 0.3
MINIMO_ALUNNI = 10


def carica_unita() -> pd.DataFrame:
    df = pd.read_csv(INPUT)
    df = df[df['alunni_totali']>9]
    df.loc[df["classi_esatte"].isna(), "classi_esatte"] = 1
    df["capienza"] = df["classi_esatte"] * ALUNNI_PER_CLASSE
    # escludiamo classi solo stranieri
    df = df[df["m_min_irrisolvibile"] == 0].copy()
    df["rimanenza"] = (df["capienza"] - df["alunni_totali"]).clip(lower=0)

    # Massimo intero x tale che (F + x) / (N + x) <= 3/10, con F = alunni non
    # nati in Italia (proxy di chi non conosce l'italiano; gli stranieri nati
    # in Italia contano come italiani, come in analyze.py/simulate_realloc.py).
    # Il floor è necessario: arrotondare al più vicino può superare la soglia.
    df["disponibilita_stranieri"] = (
        (3 * df["alunni_totali"] - 10 * df["alunni_non_nati_in_Italia"]) // 7
    )

    # I due vincoli valgono contemporaneamente. Le unità già sopra soglia
    # hanno headroom negativo e quindi disponibilità ricevibile pari a zero.
    df["disponibilita_effettiva"] = df[
        ["rimanenza", "disponibilita_stranieri"]
    ].min(axis=1).clip(lower=0)
    return df[df["anno_corso"] == 1]


def comuni_con_cambio(df: pd.DataFrame, consenti_cambio_tipo_scuola: bool) -> pd.DataFrame:
    chiavi = ["codice_comune", "comune", "provincia", "ordine_scuola"]
    if not consenti_cambio_tipo_scuola:
        chiavi.append("tipo_scuola_anagrafe")

    gruppi = (
        df.groupby(chiavi, dropna=False)
        .agg(studenti_da_spostare=("m_min", "sum"),
             disponibilita_effettiva=("disponibilita_effettiva", "sum"))
        .reset_index()
    )
    gruppi["studenti_senza_posto"] = gruppi["studenti_da_spostare"] - gruppi["disponibilita_effettiva"]
    return gruppi[gruppi["studenti_senza_posto"] > 0].sort_values(
        "studenti_senza_posto", ascending=False
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--consenti-cambio-tipo-scuola", action="store_true",
                        help="Ignora il vincolo su tipo_scuola_anagrafe (raggruppa solo per comune e ordine_scuola).")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    df = carica_unita()
    voci = comuni_con_cambio(df, args.consenti_cambio_tipo_scuola)

    n_comuni = voci["codice_comune"].nunique()
    n_comuni_totali = df["codice_comune"].nunique()
    print(f"Comuni con deficit di posti interni nello scenario modellato: "
          f"{n_comuni} su {n_comuni_totali} ({n_comuni / n_comuni_totali:.1%})")
    print(f"Deficit di posti nel proprio comune: {int(voci['studenti_senza_posto'].sum())}")

    suffisso = "_cambio_tipo" if args.consenti_cambio_tipo_scuola else ""
    out = RESULTS / f"comuni_cambio_comune_202425{suffisso}.csv"
    voci.to_csv(out, index=False)
    print(f"Dettaglio salvato in {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
