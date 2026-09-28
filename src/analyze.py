#!/usr/bin/env python3
"""Analisi del criterio del 30% sui dati MIM dell'a.s. 2024/25.

La base statistica è il flusso MIM per cittadinanza. Il flusso classi/studenti
serve per controllare i totali e aggiungere il numero di classi quando la
chiave del corso coincide. Le anagrafiche sono unite tramite CodiceScuola.

Si analizzano solo le scuole statali con caratteristica anagrafica NORMALE e
tutte le paritarie (la cui anagrafe non ha il campo). Le righe perse nei join
sono tracciate in results/controlli_join_<anno>.csv.

Il criterio del 30% è applicato agli alunni che si stima non conoscano
l'italiano, non all'intera cittadinanza non italiana. Come proxy si usano gli
alunni stranieri NON nati in Italia: per ogni unità
`alunni_non_nati_in_Italia = round_half_up(F * quota)`, con
`quota = (100 - per100) / 100` presa per regione e ordine di scuola dalla
distribuzione di riferimento MIM 2022/23 (colonne `*_per100` = nati in Italia
ogni 100 alunni stranieri). Gli stranieri nati in Italia contano come italiani
a tutti gli effetti: `alunni_nati_in_Italia = alunni_totali -
alunni_non_nati_in_Italia`. `sopra_30`, `m_min` e derivati sono calcolati su
questi conteggi; `alunni_italiani` / `alunni_non_italiani` restano i conteggi
per cittadinanza.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data_raw"
PROCESSED = ROOT / "data_processed"
RESULTS = ROOT / "results"
METADATA = ROOT / "metadata"
REFERENCE_SHARES = (
    ROOT
    / "distribuzioni_di_riferimento"
    / "alunni_cittadinanza_non_italiana_nati_in_italia_2022_2023.csv"
)
YEAR = "202425"
YEAR_LABEL = "2024/25"
THRESHOLD_NUM = 3
THRESHOLD_DEN = 10
# Solo le statali hanno DESCRIZIONECARATTERISTICASCUOLA; le paritarie non vengono filtrate.
CARATTERISTICA_AMMESSA = "NORMALE"
CARATTERISTICA_NON_DISPONIBILE = "NON DISPONIBILE (PARITARIA)"

# Regioni della distribuzione di riferimento -> campo REGIONE MIM.
REFERENCE_REGIONS = {
    "Piemonte": "PIEMONTE",
    "Valle d'Aosta": "VALLE D'AOSTA",
    "Lombardia": "LOMBARDIA",
    "Trentino A.A.": "TRENTINO-ALTO ADIGE",
    "Veneto": "VENETO",
    "Friuli V.G.": "FRIULI-VENEZIA G.",
    "Liguria": "LIGURIA",
    "E. Romagna": "EMILIA ROMAGNA",
    "Toscana": "TOSCANA",
    "Umbria": "UMBRIA",
    "Marche": "MARCHE",
    "Lazio": "LAZIO",
    "Abruzzo": "ABRUZZO",
    "Molise": "MOLISE",
    "Campania": "CAMPANIA",
    "Puglia": "PUGLIA",
    "Basilicata": "BASILICATA",
    "Calabria": "CALABRIA",
    "Sicilia": "SICILIA",
    "Sardegna": "SARDEGNA",
}
# Colonne "nati in Italia ogni 100 alunni stranieri" -> ORDINESCUOLA MIM.
REFERENCE_ORDERS = {
    "primaria_per100": "SCUOLA PRIMARIA",
    "secondaria_I_per100": "SCUOLA SECONDARIA I GRADO",
    "secondaria_II_per100": "SCUOLA SECONDARIA II GRADO",
}


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
    "caratteristica_scuola",
    "fonte_anagrafe",
    "anagrafe_mappata",
    "alunni_italiani",
    "alunni_non_italiani",
    "alunni_totali",
    "quota_non_nati_in_Italia_riferimento",
    "alunni_non_nati_in_Italia",
    "alunni_nati_in_Italia",
    "quota_non_nati_in_Italia",
    "sopra_30",
    "m_min",
    "m_min_irrisolvibile",
    "m_min_con_sostituzione_legacy",
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
    "unita_sopra_30_irrisolvibili",
    "classi_sopra_trenta",
    "studenti_totali_sopra_30",
    "studenti_non_italiani_sopra_30",
    "studenti_non_nati_in_Italia_sopra_30",
    "m_min_sopra_30",
    "m_min_pct_non_nati_in_Italia_sopra_30",
    "m_min_pct_studenti_sopra_30",
    "m_min_con_sostituzione_legacy_sopra_30",
    "studenti_totali_analizzati",
    "studenti_non_italiani_analizzati",
    "studenti_non_nati_in_Italia_analizzati",
    "m_min_pct_non_nati_in_Italia_analizzati",
    "m_min_pct_studenti_analizzati",
    "classi_esatte_sommate",
    "unita_con_chiave_classi_esatta",
    "unita_senza_chiave_classi_esatta",
]

EXCLUDED_FIELDS = [
    "anno_scolastico",
    "tipo_gestione",
    "codice_scuola",
    "denominazione_scuola",
    "codice_istituto_riferimento",
    "ordine_scuola",
    "anno_corso",
    "regione",
    "provincia",
    "comune",
    "tipo_scuola_anagrafe",
    "caratteristica_scuola",
    "alunni_italiani",
    "alunni_non_italiani",
    "alunni_totali",
    "motivo_esclusione",
]

JOIN_QC_FIELDS = [
    "anno_scolastico",
    "tipo_gestione",
    "dataset",
    "passaggio",
    "esito",
    "righe",
    "plessi",
    "alunni",
    "nota",
]


def read_csv(path: Path) -> pd.DataFrame:
    """Legge tutti i campi come testo, preservando codici e campi vuoti."""

    return pd.read_csv(
        path,
        dtype=str,
        encoding="utf-8-sig",
        keep_default_na=False,
    )


def write_csv(
    path: Path,
    rows: pd.DataFrame | list[dict[str, object]],
    fields: list[str],
) -> None:
    """Scrive le colonne richieste con lo stesso formato CSV usato finora."""

    path.parent.mkdir(parents=True, exist_ok=True)
    table = rows if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows, columns=fields)
    table.to_csv(
        path,
        columns=fields,
        index=False,
        encoding="utf-8",
        lineterminator="\r\n",
        na_rep="",
    )


def text_column(table: pd.DataFrame, field: str) -> pd.Series:
    """Normalizza un campo testuale senza convertirne gli identificativi."""

    return table[field].astype(str).str.strip()


def integer_column(table: pd.DataFrame, field: str) -> pd.Series:
    """Converte un campo numerico MIM in interi; i vuoti valgono zero."""

    values = text_column(table, field).replace("", "0")
    return values.map(int).astype("int64")


def numeric_sum(values: pd.Series) -> int:
    """Somma valori numerici che possono contenere stringhe vuote."""

    return int(pd.to_numeric(values, errors="coerce").fillna(0).sum())


def pct(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return ""
    return f"{numerator / denominator:.6f}"


def ceil_excess_con_sostituzione(f: int, n: int) -> int:
    """Formula legacy, valida solo se ogni studente spostato viene sostituito."""

    excess = THRESHOLD_DEN * f - THRESHOLD_NUM * n
    if excess <= 0:
        return 0
    return (excess + THRESHOLD_DEN - 1) // THRESHOLD_DEN


def ceil_excess_senza_sostituzione(f: int, n: int) -> tuple[int | None, bool]:
    """Minimo m con (F-m)/(N-m) <= 30%, spostando alunni senza sostituzione."""

    if n == f and f > 0:
        return None, True

    excess = THRESHOLD_DEN * f - THRESHOLD_NUM * n
    if excess <= 0:
        return 0, False

    denominator = THRESHOLD_DEN - THRESHOLD_NUM
    return (excess + denominator - 1) // denominator, False


def load_non_born_in_italy_shares() -> dict[tuple[str, str], tuple[int, int]]:
    """Quota di alunni stranieri non nati in Italia per (regione, ordine_scuola).

    La quota è restituita come frazione esatta (numeratore, denominatore) per
    arrotondare senza errori di virgola mobile: per100 ha un solo decimale.
    """

    table = read_csv(REFERENCE_SHARES)
    shares: dict[tuple[str, str], tuple[int, int]] = {}
    for _, row in table.iterrows():
        name = row["regione"].strip()
        if name == "Italia":
            continue
        if name not in REFERENCE_REGIONS:
            raise ValueError(f"Regione non mappata nella distribuzione di riferimento: {name!r}")
        for column, order in REFERENCE_ORDERS.items():
            born_in_italy_tenths = round(float(row[column]) * 10)
            shares[(REFERENCE_REGIONS[name], order)] = (1000 - born_in_italy_tenths, 1000)
    return shares


def round_half_up(numerator: int, denominator: int) -> int:
    """Arrotonda numerator/denominator (non negativi) all'intero, 0.5 verso l'alto."""

    return (2 * numerator + denominator) // (2 * denominator)


def source_path(dataset: str, management: str) -> Path:
    suffix = "STA" if management == "statale" else "PAR"
    return RAW / f"{dataset}{suffix}{YEAR}20250831.csv"


def load_registry(management: str) -> tuple[pd.DataFrame, dict[str, int]]:
    """Unisce le anagrafiche standard e autonome, mantenendo il primo codice."""

    suffix = "STAT" if management == "statale" else "PAR"
    standard = read_csv(RAW / f"SCUANAGRAFE{suffix}{YEAR}20250831.csv")
    autonomous = read_csv(RAW / f"SCUANAAUT{suffix}{YEAR}20250831.csv")
    standard["fonte_anagrafe"] = "standard"
    autonomous["fonte_anagrafe"] = "autonome"
    rows = pd.concat([standard, autonomous], ignore_index=True)

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
    rows["codice_scuola"] = text_column(rows, "CODICESCUOLA")
    rows = rows.loc[rows["codice_scuola"].ne("")].copy()
    duplicate_codes = int(rows["codice_scuola"].duplicated().sum())
    rows = rows.drop_duplicates("codice_scuola", keep="first").copy()

    for target, source in common_fields.items():
        rows[target] = text_column(rows, source)

    # Codice istituto e caratteristica esistono solo nelle anagrafiche statali.
    is_state = management == "statale"
    rows["codice_istituto_riferimento"] = (
        text_column(rows, "CODICEISTITUTORIFERIMENTO") if is_state else ""
    )
    rows["denominazione_istituto_riferimento"] = (
        text_column(rows, "DENOMINAZIONEISTITUTORIFERIMENTO") if is_state else ""
    )
    rows["caratteristica_scuola"] = (
        text_column(rows, "DESCRIZIONECARATTERISTICASCUOLA")
        if is_state
        else CARATTERISTICA_NON_DISPONIBILE
    )
    rows["anagrafe_mappata"] = "1"

    registry_fields = [
        "codice_scuola",
        "denominazione_scuola",
        "codice_istituto_riferimento",
        "denominazione_istituto_riferimento",
        "area_geografica",
        "regione",
        "provincia",
        "codice_comune",
        "comune",
        "indirizzo_scuola",
        "cap_scuola",
        "tipo_scuola_anagrafe",
        "caratteristica_scuola",
        "fonte_anagrafe",
        "anagrafe_mappata",
    ]
    diagnostics = {
        "standard_rows": len(standard),
        "autonomous_rows": len(autonomous),
        "duplicate_codes": duplicate_codes,
    }
    return rows.loc[:, registry_fields], diagnostics


def load_class_index(
    management: str,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Prepara il flusso classi/studenti; l'anno 7 non è una chiave esatta."""

    rows = read_csv(source_path("ALUCORSOINDCLA", management))
    key_fields = ["CODICESCUOLA", "ORDINESCUOLA", "ANNOCORSOCLASSE"]
    for field in key_fields:
        rows[field] = text_column(rows, field)

    rows["classi"] = integer_column(rows, "CLASSI")
    rows["alunni_classi"] = integer_column(rows, "ALUNNIMASCHI") + integer_column(
        rows, "ALUNNIFEMMINE"
    )
    rows["anno_7"] = rows["ANNOCORSOCLASSE"].eq("7")
    duplicate_keys = int(rows.loc[~rows["anno_7"]].duplicated(key_fields).sum())
    rows = rows.rename(
        columns={
            "CODICESCUOLA": "codice_scuola",
            "ORDINESCUOLA": "ordine_scuola",
            "ANNOCORSOCLASSE": "anno_corso",
        }
    )

    diagnostics = {
        "rows": len(rows),
        "rows_course_7": int(rows["anno_7"].sum()),
        "students_total": int(rows["alunni_classi"].sum()),
        "classes_total": int(rows["classi"].sum()),
        "duplicate_keys": duplicate_keys,
    }
    # Tutte le righe, anno 7 incluso: servono anche per il controllo dei join.
    return (
        rows.loc[
            :,
            ["codice_scuola", "ordine_scuola", "anno_corso", "anno_7", "classi", "alunni_classi"],
        ],
        diagnostics,
    )


def join_row(
    management: str,
    dataset: str,
    step: str,
    outcome: str,
    table: pd.DataFrame,
    students_field: str | None,
    note: str = "",
) -> dict[str, object]:
    """Una riga del controllo sui join: quante righe, plessi e alunni finiscono in un esito."""

    return {
        "anno_scolastico": YEAR,
        "tipo_gestione": management,
        "dataset": dataset,
        "passaggio": step,
        "esito": outcome,
        "righe": len(table),
        "plessi": int(table["codice_scuola"].nunique()),
        "alunni": int(table[students_field].sum()) if students_field else "",
        "nota": note,
    }


def build_join_qc(
    management: str,
    registry: pd.DataFrame,
    registry_diag: dict[str, int],
    class_index: pd.DataFrame,
    all_units: pd.DataFrame,
    units: pd.DataFrame,
    course_key: list[str],
) -> list[dict[str, object]]:
    """Traccia dove finiscono le righe di anagrafe, cittadinanza e classi nei join.

    Per ogni dataset gli esiti del passaggio "join" sono disgiunti e sommano al
    totale del passaggio "caricamento".
    """

    rows: list[dict[str, object]] = []
    n_field = "alunni_totali"

    # Anagrafe
    citizenship_codes = set(all_units["codice_scuola"])
    rows.append(
        join_row(
            management, "anagrafe", "caricamento", "codici_unici", registry, None,
            f"{registry_diag['standard_rows']} righe standard + "
            f"{registry_diag['autonomous_rows']} autonome; "
            f"{registry_diag['duplicate_codes']} codici duplicati scartati (si tiene il primo).",
        )
    )
    in_citizenship = registry["codice_scuola"].isin(citizenship_codes)
    rows.append(
        join_row(
            management, "anagrafe", "join con cittadinanza", "codice_presente_in_cittadinanza",
            registry.loc[in_citizenship], None,
        )
    )
    rows.append(
        join_row(
            management, "anagrafe", "join con cittadinanza", "codice_assente_da_cittadinanza",
            registry.loc[~in_citizenship], None,
            "Plessi senza alunni di primaria/secondaria: infanzia, sedi di istituto, plessi chiusi.",
        )
    )

    # Cittadinanza
    rows.append(join_row(management, "cittadinanza", "caricamento", "righe_totali", all_units, n_field))
    reasons = all_units["motivo_esclusione"]
    rows.append(
        join_row(
            management, "cittadinanza", "join con anagrafe", "esclusa_anagrafe_mancante",
            all_units.loc[reasons.eq("anagrafe_mancante")], n_field,
        )
    )
    not_normal = all_units.loc[reasons.eq("caratteristica_non_normale")]
    by_characteristic = (
        not_normal.groupby("caratteristica_scuola")[n_field].sum().sort_values(ascending=False)
    )
    for characteristic in by_characteristic.index:
        rows.append(
            join_row(
                management, "cittadinanza", "join con anagrafe",
                f"esclusa_caratteristica: {characteristic}",
                not_normal.loc[not_normal["caratteristica_scuola"].eq(characteristic)], n_field,
            )
        )
    rows.append(
        join_row(
            management, "cittadinanza", "join con anagrafe", "inclusa_nell_analisi",
            all_units.loc[reasons.eq("")], n_field,
            f"Solo caratteristica {CARATTERISTICA_AMMESSA}."
            if management == "statale"
            else "Filtro sulla caratteristica non applicabile: campo assente nell'anagrafe paritarie.",
        )
    )

    # Unità incluse rispetto al flusso classi (sottoinsieme di "inclusa_nell_analisi")
    course_seven_codes = set(class_index.loc[class_index["anno_7"], "codice_scuola"])
    matched = units["chiave_classi_confrontabile"].eq(1)
    in_course_seven = units["codice_scuola"].isin(course_seven_codes)
    rows.append(
        join_row(
            management, "cittadinanza (incluse)", "join con classi", "chiave_classi_esatta",
            units.loc[matched], n_field,
        )
    )
    rows.append(
        join_row(
            management, "cittadinanza (incluse)", "join con classi",
            "senza_chiave_classi_plesso_con_pluriclassi",
            units.loc[~matched & in_course_seven], n_field,
            "Alunni in pluriclasse: nel flusso classi sono sotto l'anno di corso 7.",
        )
    )
    rows.append(
        join_row(
            management, "cittadinanza (incluse)", "join con classi",
            "senza_chiave_classi_altro",
            units.loc[~matched & ~in_course_seven], n_field,
        )
    )

    # Classi
    class_field = "alunni_classi"
    included_codes = set(units["codice_scuola"])
    excluded_codes = citizenship_codes - included_codes
    included_keys = units.loc[:, course_key].assign(_unita_inclusa=True)
    classes = class_index.merge(included_keys, on=course_key, how="left", sort=False)
    classes["_unita_inclusa"] = classes["_unita_inclusa"].eq(True)
    plesso_included = classes["codice_scuola"].isin(included_codes)
    rows.append(join_row(management, "classi", "caricamento", "righe_totali", classes, class_field))
    rows.append(
        join_row(
            management, "classi", "join con cittadinanza", "unita_a_unita_incluse",
            classes.loc[plesso_included & ~classes["anno_7"] & classes["_unita_inclusa"]],
            class_field,
        )
    )
    rows.append(
        join_row(
            management, "classi", "join con cittadinanza", "plesso_incluso_anno_7_pluriclasse",
            classes.loc[plesso_included & classes["anno_7"]], class_field,
            "Non unibili per costruzione: la pluriclasse mescola più anni di corso.",
        )
    )
    rows.append(
        join_row(
            management, "classi", "join con cittadinanza", "plesso_incluso_chiave_senza_unita",
            classes.loc[plesso_included & ~classes["anno_7"] & ~classes["_unita_inclusa"]],
            class_field,
        )
    )
    rows.append(
        join_row(
            management, "classi", "join con cittadinanza", "plesso_escluso_dall_analisi",
            classes.loc[classes["codice_scuola"].isin(excluded_codes)], class_field,
            "Plessi scartati nel join cittadinanza-anagrafe (caratteristica o anagrafe mancante).",
        )
    )
    rows.append(
        join_row(
            management, "classi", "join con cittadinanza", "plesso_assente_da_cittadinanza",
            classes.loc[~classes["codice_scuola"].isin(citizenship_codes)], class_field,
        )
    )
    return rows


def load_units(
    management: str,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object], list[dict[str, object]]]:
    """Carica le unità per cittadinanza, le filtra e vi unisce anagrafe e classi.

    Restituisce le unità incluse, quelle escluse con il motivo, le diagnostiche
    e il controllo dei join.
    """

    registry, registry_diag = load_registry(management)
    class_index, class_diag = load_class_index(management)
    raw_units = read_csv(source_path("ALUITASTRACIT", management))

    key_fields = ["CODICESCUOLA", "ORDINESCUOLA", "ANNOCORSO"]
    for field in key_fields:
        raw_units[field] = text_column(raw_units, field)

    n = integer_column(raw_units, "ALUNNI")
    italiani = integer_column(raw_units, "ALUNNICITTADINANZAITALIANA")
    non_italiani = integer_column(raw_units, "ALUNNICITTADINANZANONITALIANA")

    inconsistent = n.ne(italiani + non_italiani)
    if inconsistent.any():
        row = raw_units.loc[inconsistent].iloc[0]
        key = (row["CODICESCUOLA"], row["ORDINESCUOLA"], row["ANNOCORSO"])
        position = inconsistent[inconsistent].index[0]
        raise ValueError(
            f"ALUNNI != italiani + non italiani in {management} {key}: "
            f"{n.loc[position]} != {italiani.loc[position]} + {non_italiani.loc[position]}"
        )
    else:
        print("NESSUNA INCONSISTENZA SUL NUMERO DI ALUNNI. BENE!")
    if n.le(0).any():
        position = n[n.le(0)].index[0]
        row = raw_units.loc[position]
        key = (row["CODICESCUOLA"], row["ORDINESCUOLA"], row["ANNOCORSO"])
        raise ValueError(f"ALUNNI non positivo in {management} {key}: {n.loc[position]}")

    units = pd.DataFrame(
        {
            "anno_scolastico": YEAR,
            "tipo_gestione": management,
            "codice_scuola": raw_units["CODICESCUOLA"],
            "ordine_scuola": raw_units["ORDINESCUOLA"],
            "anno_corso": raw_units["ANNOCORSO"],
            "alunni_italiani": italiani,
            "alunni_non_italiani": non_italiani,
            "alunni_totali": n,
        }
    )

    # Il codice scuola identifica il plesso nell'anagrafe.
    units = units.merge(registry, on="codice_scuola", how="left", sort=False)
    registry_missing = units["fonte_anagrafe"].isna()
    for field in registry.columns:
        units[field] = units[field].fillna("")

    # Si tengono solo i plessi presenti in anagrafe e, per le statali, con
    # caratteristica NORMALE (esclusi serali, carceri, CPIA, ospedali, convitti...).
    if management == "statale":
        not_normal = ~registry_missing & units["caratteristica_scuola"].ne(CARATTERISTICA_AMMESSA)
    else:
        not_normal = pd.Series(False, index=units.index)
    units["motivo_esclusione"] = ""
    units.loc[registry_missing, "motivo_esclusione"] = "anagrafe_mancante"
    units.loc[not_normal, "motivo_esclusione"] = "caratteristica_non_normale"
    all_units = units
    excluded = units.loc[units["motivo_esclusione"].ne("")].reset_index(drop=True)
    units = units.loc[units["motivo_esclusione"].eq("")].reset_index(drop=True)

    # Solo gli stranieri non nati in Italia (proxy di chi non conosce
    # l'italiano) contano per il 30%; quelli nati in Italia valgono come italiani.
    shares = load_non_born_in_italy_shares()
    share_keys = list(zip(units["regione"], units["ordine_scuola"]))
    missing_shares = sorted(set(share_keys) - set(shares))
    if missing_shares:
        raise ValueError(f"Quota non nati in Italia mancante per (regione, ordine): {missing_shares}")
    units["quota_non_nati_in_Italia_riferimento"] = [
        f"{shares[key][0] / shares[key][1]:.3f}" for key in share_keys
    ]
    units["alunni_non_nati_in_Italia"] = pd.Series(
        [
            round_half_up(int(f) * shares[key][0], shares[key][1])
            for f, key in zip(units["alunni_non_italiani"], share_keys)
        ],
        index=units.index,
        dtype="int64",
    )
    units["alunni_nati_in_Italia"] = units["alunni_totali"] - units["alunni_non_nati_in_Italia"]

    n = units["alunni_totali"]
    non_nati = units["alunni_non_nati_in_Italia"]

    # Per il flusso classi la chiave esatta è plesso + ordine + anno di corso.
    course_key = ["codice_scuola", "ordine_scuola", "anno_corso"]
    exact_classes = class_index.loc[~class_index["anno_7"]].drop_duplicates(course_key, keep="first")
    units = units.merge(
        exact_classes.drop(columns="anno_7"), on=course_key, how="left", sort=False
    )
    class_match = units["classi"].notna()
    units["classi_esatte"] = [int(value) if pd.notna(value) else "" for value in units["classi"]]
    units["alunni_classi_esatte"] = [
        int(value) if pd.notna(value) else "" for value in units["alunni_classi"]
    ]
    units["delta_n_cittadinanza_meno_classi"] = [
        int(total) - int(class_total) if matched else ""
        for total, class_total, matched in zip(n, units["alunni_classi"], class_match)
    ]
    units["chiave_classi_confrontabile"] = class_match.astype("int64")

    # Il confronto esatto evita arrotondamenti della percentuale.
    excess = THRESHOLD_DEN * non_nati - THRESHOLD_NUM * n
    units["sopra_30"] = excess.gt(0).astype("int64")
    minimums = [
        ceil_excess_senza_sostituzione(int(f), int(total))
        for f, total in zip(non_nati, n)
    ]
    units["m_min"] = [minimum if not impossible else "" for minimum, impossible in minimums]
    units["m_min_irrisolvibile"] = [int(impossible) for _, impossible in minimums]
    units["m_min_con_sostituzione_legacy"] = [
        ceil_excess_con_sostituzione(int(f), int(total)) for f, total in zip(non_nati, n)
    ]
    units["quota_non_nati_in_Italia"] = [
        f"{int(f) / int(total):.6f}" for f, total in zip(non_nati, n)
    ]

    join_rows = build_join_qc(
        management, registry, registry_diag, class_index, all_units, units, course_key
    )

    above = units.loc[units["sopra_30"].eq(1)]
    diagnostics: dict[str, object] = {
        "management": management,
        "citizenship_rows": len(raw_units),
        "citizenship_duplicate_keys": int(raw_units.duplicated(key_fields).sum()),
        "citizenship_n_total": int(all_units["alunni_totali"].sum()),
        "citizenship_f_total": int(all_units["alunni_non_italiani"].sum()),
        "citizenship_italiani_total": int(all_units["alunni_italiani"].sum()),
        "excluded_units": len(excluded),
        "excluded_n_total": int(excluded["alunni_totali"].sum()),
        "excluded_f_total": int(excluded["alunni_non_italiani"].sum()),
        "included_units": len(units),
        "included_n_total": int(n.sum()),
        "included_f_total": int(units["alunni_non_italiani"].sum()),
        "included_non_nati_total": int(non_nati.sum()),
        "above_30_units": len(above),
        "above_30_n_total": int(above["alunni_totali"].sum()),
        "above_30_f_total": int(above["alunni_non_italiani"].sum()),
        "above_30_non_nati_total": int(above["alunni_non_nati_in_Italia"].sum()),
        "above_30_m_min_total": numeric_sum(above["m_min"]),
        "above_30_m_min_con_sostituzione_total": int(
            above["m_min_con_sostituzione_legacy"].sum()
        ),
        "above_30_irrisolvibili": int(above["m_min_irrisolvibile"].sum()),
        "registry_missing_units": int(registry_missing.sum()),
        "class_exact_matches": int(class_match.sum()),
        "class_missing_exact": int((~class_match).sum()),
        "class_delta_nonzero": int(
            pd.to_numeric(
                units.loc[class_match, "delta_n_cittadinanza_meno_classi"]
            ).ne(0).sum()
        ),
        "class_delta_sum": numeric_sum(units["delta_n_cittadinanza_meno_classi"]),
        "class_rows": class_diag["rows"],
        "class_course_7_rows": class_diag["rows_course_7"],
        "classes_students_total": class_diag["students_total"],
        "classes_total": class_diag["classes_total"],
        "class_duplicate_keys": class_diag["duplicate_keys"],
        "registry_standard_rows": registry_diag["standard_rows"],
        "registry_autonomous_rows": registry_diag["autonomous_rows"],
        "registry_duplicate_codes": registry_diag["duplicate_codes"],
    }
    return units.loc[:, UNIT_FIELDS], excluded.loc[:, EXCLUDED_FIELDS], diagnostics, join_rows


def aggregate_rows(
    rows: pd.DataFrame,
    level: str,
    group_fields: list[str],
    management_label: str,
) -> pd.DataFrame:
    """Calcola i totali per gruppo mantenendo il flag deciso a livello unità."""

    work = rows.copy()
    flagged = work["sopra_30"]
    work["_unita"] = 1
    work["_irrisolvibili_sopra_30"] = work["m_min_irrisolvibile"] * flagged
    # Le scuole senza classi_esatte valgono una classe sola.
    work["_classi_per_unita"] = pd.to_numeric(work["classi_esatte"], errors="coerce").fillna(1)
    work["_classi_sopra_30"] = work["_classi_per_unita"] * flagged
    work["_studenti_totali_sopra_30"] = work["alunni_totali"] * flagged
    work["_studenti_non_italiani_sopra_30"] = work["alunni_non_italiani"] * flagged
    work["_studenti_non_nati_in_Italia_sopra_30"] = work["alunni_non_nati_in_Italia"] * flagged
    work["_m_min_sopra_30"] = pd.to_numeric(work["m_min"], errors="coerce").fillna(0) * flagged
    work["_m_min_legacy_sopra_30"] = work["m_min_con_sostituzione_legacy"] * flagged
    work["_classi_esatte"] = pd.to_numeric(work["classi_esatte"], errors="coerce").fillna(0)

    # Un campo costante permette di usare lo stesso groupby anche per il totale nazionale.
    group_by = group_fields or ["_gruppo_unico"]
    if not group_fields:
        work["_gruppo_unico"] = "tutte"

    grouped = work.groupby(group_by, sort=False, dropna=False).agg(
        unita_totali=("_unita", "sum"),
        unita_sopra_30=("sopra_30", "sum"),
        unita_sopra_30_irrisolvibili=("_irrisolvibili_sopra_30", "sum"),
        classi_sopra_trenta=("_classi_sopra_30", "sum"),
        studenti_totali_sopra_30=("_studenti_totali_sopra_30", "sum"),
        studenti_non_italiani_sopra_30=("_studenti_non_italiani_sopra_30", "sum"),
        studenti_non_nati_in_Italia_sopra_30=("_studenti_non_nati_in_Italia_sopra_30", "sum"),
        m_min_sopra_30=("_m_min_sopra_30", "sum"),
        m_min_con_sostituzione_legacy_sopra_30=("_m_min_legacy_sopra_30", "sum"),
        studenti_totali_analizzati=("alunni_totali", "sum"),
        studenti_non_italiani_analizzati=("alunni_non_italiani", "sum"),
        studenti_non_nati_in_Italia_analizzati=("alunni_non_nati_in_Italia", "sum"),
        classi_esatte_sommate=("_classi_esatte", "sum"),
        unita_con_chiave_classi_esatta=("chiave_classi_confrontabile", "sum"),
    ).reset_index()

    result = pd.DataFrame(
        {
            "anno_scolastico": YEAR,
            "livello_aggregazione": level,
            "tipo_gestione": management_label,
            "regione": "",
            "provincia": "",
            "codice_comune": "",
            "comune": "",
            "codice_scuola": "",
            "denominazione_scuola": "",
        },
        index=grouped.index,
    )
    for field in group_fields:
        result[field] = grouped[field]
    for field in [
        "unita_totali",
        "unita_sopra_30",
        "unita_sopra_30_irrisolvibili",
        "classi_sopra_trenta",
        "studenti_totali_sopra_30",
        "studenti_non_italiani_sopra_30",
        "studenti_non_nati_in_Italia_sopra_30",
        "m_min_sopra_30",
        "m_min_con_sostituzione_legacy_sopra_30",
        "studenti_totali_analizzati",
        "studenti_non_italiani_analizzati",
        "studenti_non_nati_in_Italia_analizzati",
        "classi_esatte_sommate",
        "unita_con_chiave_classi_esatta",
    ]:
        result[field] = grouped[field].astype("int64")

    above_m = result["m_min_sopra_30"]
    result["m_min_pct_non_nati_in_Italia_sopra_30"] = [
        pct(int(m), int(f))
        for m, f in zip(above_m, result["studenti_non_nati_in_Italia_sopra_30"])
    ]
    result["m_min_pct_studenti_sopra_30"] = [
        pct(int(m), int(n)) for m, n in zip(above_m, result["studenti_totali_sopra_30"])
    ]
    result["m_min_pct_non_nati_in_Italia_analizzati"] = [
        pct(int(m), int(f))
        for m, f in zip(above_m, result["studenti_non_nati_in_Italia_analizzati"])
    ]
    result["m_min_pct_studenti_analizzati"] = [
        pct(int(m), int(n)) for m, n in zip(above_m, result["studenti_totali_analizzati"])
    ]
    result["unita_senza_chiave_classi_esatta"] = (
        result["unita_totali"] - result["unita_con_chiave_classi_esatta"]
    )
    return result


def build_aggregates(units: pd.DataFrame) -> pd.DataFrame:
    levels = [
        (
            "plesso",
            [
                "codice_scuola",
                "denominazione_scuola",
                "codice_comune",
                "comune",
                "provincia",
                "regione",
            ],
        ),
        ("comune", ["codice_comune", "comune", "provincia", "regione"]),
        ("provincia", ["provincia", "regione"]),
        ("regione", ["regione"]),
        ("nazionale", []),
    ]
    managements = [
        ("tutte", units),
        ("statale", units.loc[units["tipo_gestione"].eq("statale")]),
        ("paritaria", units.loc[units["tipo_gestione"].eq("paritaria")]),
    ]

    output: list[pd.DataFrame] = []
    for management_label, subset in managements:
        for level, fields in levels:
            output.append(aggregate_rows(subset, level, fields, management_label))

    aggregates = pd.concat(output, ignore_index=True).loc[:, AGG_FIELDS]
    level_order = {"nazionale": 0, "regione": 1, "provincia": 2, "comune": 3, "plesso": 4}
    aggregates["_ordine_livello"] = aggregates["livello_aggregazione"].map(level_order)
    return (
        aggregates.sort_values(
            ["tipo_gestione", "_ordine_livello", "regione", "provincia", "comune", "codice_scuola"],
            kind="mergesort",
        )
        .drop(columns="_ordine_livello")
        .loc[:, AGG_FIELDS]
        .reset_index(drop=True)
    )


def make_qc_row(metric: str, value: object, management: str, note: str = "") -> dict[str, object]:
    return {
        "anno_scolastico": YEAR,
        "metrica": metric,
        "tipo_gestione": management,
        "valore": value,
        "nota": note,
    }


def build_qc(
    diagnostics: list[dict[str, object]], units: pd.DataFrame
) -> pd.DataFrame:
    qc: list[dict[str, object]] = []
    for diag in diagnostics:
        management = str(diag["management"])
        qc.extend(
            [
                make_qc_row("righe_studenti_cittadinanza", diag["citizenship_rows"], management),
                make_qc_row("studenti_totali_cittadinanza", diag["citizenship_n_total"], management),
                make_qc_row("studenti_non_italiani_cittadinanza", diag["citizenship_f_total"], management),
                make_qc_row(
                    "unità_escluse",
                    diag["excluded_units"],
                    management,
                    f"Anagrafe mancante o caratteristica diversa da {CARATTERISTICA_AMMESSA} "
                    f"(solo statali). Dettaglio in controlli_join_{YEAR}.csv e unita_escluse_{YEAR}.csv.",
                ),
                make_qc_row("studenti_esclusi", diag["excluded_n_total"], management),
                make_qc_row("non_italiani_esclusi", diag["excluded_f_total"], management),
                make_qc_row("unità_incluse", diag["included_units"], management),
                make_qc_row(
                    "studenti_inclusi",
                    diag["included_n_total"],
                    management,
                    "N base dell'analisi; le metriche seguenti sono calcolate solo sulle unità incluse.",
                ),
                make_qc_row("non_italiani_inclusi", diag["included_f_total"], management),
                make_qc_row(
                    "non_nati_in_Italia_inclusi",
                    diag["included_non_nati_total"],
                    management,
                    "Stima: non italiani x quota regionale per ordine di non nati in Italia "
                    "(riferimento MIM 2022/23), arrotondata per unità. Base del criterio del 30%.",
                ),
                make_qc_row("unità_sopra_30", diag["above_30_units"], management),
                make_qc_row("studenti_in_unità_sopra_30", diag["above_30_n_total"], management),
                make_qc_row("non_italiani_in_unità_sopra_30", diag["above_30_f_total"], management),
                make_qc_row(
                    "non_nati_in_Italia_in_unità_sopra_30", diag["above_30_non_nati_total"], management
                ),
                make_qc_row(
                    "m_min_in_unità_sopra_30",
                    diag["above_30_m_min_total"],
                    management,
                    "Formula senza sostituzione (N diminuisce); esclude le unità irrisolvibili.",
                ),
                make_qc_row(
                    "m_min_con_sostituzione_legacy_in_unità_sopra_30",
                    diag["above_30_m_min_con_sostituzione_total"],
                    management,
                    "Formula originaria del repository (N costante, sostituzione 1:1); sottostima il numero di spostamenti se gli studenti non vengono sostituiti.",
                ),
                make_qc_row(
                    "unità_sopra_30_irrisolvibili",
                    diag["above_30_irrisolvibili"],
                    management,
                    "Unità con zero alunni italiani (N=F): la sola rimozione di alunni non italiani non può mai portarle sotto il 30%.",
                ),
                make_qc_row("righe_dataset_classi_studenti", diag["class_rows"], management),
                make_qc_row("studenti_totali_classi_studenti", diag["classes_students_total"], management),
                make_qc_row("classi_totali", diag["classes_total"], management),
                make_qc_row("righe_classi_con_anno_7_pluriclasse", diag["class_course_7_rows"], management),
                make_qc_row("chiavi_classi_duplicate_scartate", diag["class_duplicate_keys"], management),
                make_qc_row("unità_con_chiave_classi_esatta", diag["class_exact_matches"], management),
                make_qc_row("unità_senza_chiave_classi_esatta", diag["class_missing_exact"], management),
                make_qc_row("unità_con_delta_N_nonzero", diag["class_delta_nonzero"], management),
                make_qc_row("somma_delta_N_cittadinanza_meno_classi", diag["class_delta_sum"], management),
                make_qc_row("unità_senza_anagrafica", diag["registry_missing_units"], management),
                make_qc_row("righe_anagrafe_standard", diag["registry_standard_rows"], management),
                make_qc_row("righe_anagrafe_autonome", diag["registry_autonomous_rows"], management),
                make_qc_row("codici_anagrafe_duplicati_scartati", diag["registry_duplicate_codes"], management),
            ]
        )

    qc.extend(
        [
            make_qc_row(
                "studenti_totali_dataset_classi_tutte_le_righe",
                sum(int(diag["classes_students_total"]) for diag in diagnostics),
                "tutte",
                "Confronto con il totale del flusso cittadinanza; include anche l'anno classe 7.",
            ),
            make_qc_row(
                "studenti_totali_dataset_cittadinanza",
                sum(int(diag["citizenship_n_total"]) for diag in diagnostics),
                "tutte",
                "Tutte le righe, prima del filtro sulla caratteristica.",
            ),
            make_qc_row(
                "studenti_totali_inclusi",
                int(units["alunni_totali"].sum()),
                "tutte",
                "N base dell'analisi.",
            ),
            make_qc_row(
                "studenti_totali_classi_solo_chiavi_esatte",
                numeric_sum(units["alunni_classi_esatte"]),
                "tutte",
                "Solo unità incluse; non è un confronto completo perché l'anno classe 7 non è joinabile al corso.",
            ),
        ]
    )
    return pd.DataFrame(
        qc,
        columns=["anno_scolastico", "metrica", "tipo_gestione", "valore", "nota"],
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_hashes() -> None:
    rows = [
        {"file": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)}
        for path in sorted(RAW.glob("*.csv"))
    ]
    write_csv(METADATA / "sha256_raw.csv", rows, ["file", "bytes", "sha256"])


def main() -> None:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    METADATA.mkdir(parents=True, exist_ok=True)

    unit_frames = []
    excluded_frames = []
    diagnostics = []
    join_rows = []
    for management in ("statale", "paritaria"):
        units, excluded, diagnostic, join_qc = load_units(management)
        unit_frames.append(units)
        excluded_frames.append(excluded)
        diagnostics.append(diagnostic)
        join_rows.extend(join_qc)

    excluded_units = pd.concat(excluded_frames, ignore_index=True).sort_values(
        ["tipo_gestione", "caratteristica_scuola", "codice_scuola", "ordine_scuola", "anno_corso"],
        kind="mergesort",
    )
    write_csv(PROCESSED / f"unita_escluse_{YEAR}.csv", excluded_units, EXCLUDED_FIELDS)
    write_csv(RESULTS / f"controlli_join_{YEAR}.csv", join_rows, JOIN_QC_FIELDS)

    all_units = pd.concat(unit_frames, ignore_index=True)
    all_units["_ordine_input"] = range(len(all_units))
    all_units["_anno_corso_numero"] = pd.to_numeric(all_units["anno_corso"], errors="raise").astype(
        "int64"
    )
    all_units = (
        all_units.sort_values(
            [
                "tipo_gestione",
                "regione",
                "provincia",
                "comune",
                "codice_scuola",
                "ordine_scuola",
                "_anno_corso_numero",
                "_ordine_input",
            ],
            kind="mergesort",
        )
        .drop(columns="_anno_corso_numero")
        .reset_index(drop=True)
    )
    all_units["_ordine_ordinato"] = range(len(all_units))

    #SOLO CON UNITA >= 10 STUDENTI
    all_units = all_units[all_units['alunni_totali']>=10]

    flagged = all_units.loc[all_units["sopra_30"].eq(1)].copy()
    flagged["_quota_sort"] = pd.to_numeric(flagged["quota_non_nati_in_Italia"])
    flagged["_m_min_sort"] = [
        -int(value) if value != "" else 1 for value in flagged["m_min"]
    ]
    flagged = (
        flagged.sort_values(
            ["_quota_sort", "_m_min_sort", "codice_scuola", "_ordine_ordinato"],
            ascending=[False, True, True, True],
            kind="mergesort",
        )
        .drop(columns=["_quota_sort", "_m_min_sort"])
        .reset_index(drop=True)
    )

    write_csv(PROCESSED / f"unita_{YEAR}.csv", all_units, UNIT_FIELDS)
    write_csv(PROCESSED / f"unita_sopra_30_{YEAR}.csv", flagged, UNIT_FIELDS)

    aggregates = build_aggregates(all_units)
    write_csv(RESULTS / f"aggregati_{YEAR}.csv", aggregates, AGG_FIELDS)
    national = aggregates.loc[
        aggregates["livello_aggregazione"].eq("nazionale")
        & aggregates["tipo_gestione"].eq("tutte")
    ]
    write_csv(RESULTS / f"aggregati_nazionale_{YEAR}.csv", national, AGG_FIELDS)

    qc = build_qc(diagnostics, all_units)
    qc_fields = ["anno_scolastico", "metrica", "tipo_gestione", "valore", "nota"]
    write_csv(RESULTS / f"controlli_qualita_{YEAR}.csv", qc, qc_fields)
    write_csv(RESULTS / f"top_100_unita_sopra_30_{YEAR}.csv", flagged.head(100), UNIT_FIELDS)

    summary = {
        "generated_on": date.today().isoformat(),
        "school_year": YEAR_LABEL,
        "threshold": 0.30,
        "formula": "M_min = ceil(max(0, 10F - 3N) / 7), con F = alunni non nati in Italia; spostamento SENZA sostituzione, N diminuisce di M_min",
        "definizione_F": "alunni_non_nati_in_Italia = round_half_up(alunni_non_italiani * (100 - per100_nati_in_Italia) / 100), per regione e ordine di scuola; gli stranieri nati in Italia contano come italiani",
        "fonte_quote_non_nati_in_Italia": str(REFERENCE_SHARES.relative_to(ROOT)),
        "formula_con_sostituzione_legacy": "M_min_legacy = max(0, ceil(F - 0.30*N)); assume sostituzione 1:1, N costante (formula originaria, sottostima gli spostamenti reali)",
        "unit_key": ["tipo_gestione", "CODICESCUOLA", "ORDINESCUOLA", "ANNOCORSO"],
        "filter": f"statali: DESCRIZIONECARATTERISTICASCUOLA == '{CARATTERISTICA_AMMESSA}'; paritarie: nessun filtro (campo assente); escluse le unità senza anagrafe",
        "units_excluded": len(excluded_units),
        "students_excluded": int(excluded_units["alunni_totali"].sum()),
        "units": len(all_units),
        "units_above_30": len(flagged),
        "units_above_30_irrisolvibili": int(flagged["m_min_irrisolvibile"].sum()),
        "students": int(all_units["alunni_totali"].sum()),
        "non_italian_students": int(all_units["alunni_non_italiani"].sum()),
        "students_non_nati_in_Italia": int(all_units["alunni_non_nati_in_Italia"].sum()),
        "students_in_units_above_30": int(flagged["alunni_totali"].sum()),
        "non_italian_students_in_units_above_30": int(flagged["alunni_non_italiani"].sum()),
        "students_non_nati_in_Italia_in_units_above_30": int(
            flagged["alunni_non_nati_in_Italia"].sum()
        ),
        "m_min_in_units_above_30": numeric_sum(flagged["m_min"]),
        "m_min_con_sostituzione_legacy_in_units_above_30": int(
            flagged["m_min_con_sostituzione_legacy"].sum()
        ),
        "anagrafe_missing_units": int(all_units["anagrafe_mappata"].eq("0").sum()),
        "class_exact_key_missing_units": int(all_units["chiave_classi_confrontabile"].eq(0).sum()),
        "managements": ["statale", "paritaria"],
    }
    (RESULTS / f"summary_{YEAR}.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    write_hashes()

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
