# Simulazione controfattuale del criterio del 30% — MIM a.s. 2024/25

Questo progetto calcola, come esercizio controfattuale, quante unità didattiche superano la soglia stretta del 30% di alunni con cittadinanza non italiana e quale sarebbe il minimo numero di riallocazioni uno-a-uno necessario per riportarle alla soglia, senza applicare il criterio della conoscenza dell'italiano.

## Risultato nazionale sintetico

La granularità di base è:

`tipo di gestione × CodiceScuola (plesso) × OrdineScuola × AnnoCorso`.

Per il totale combinato statali + paritarie:

| Indicatore | Valore |
|---|---:|
| Unità analizzate | 134.784 |
| Unità con `p > 0,30` | 13.806 |
| Studenti nelle unità sopra soglia | 542.790 |
| Alunni con cittadinanza non italiana nelle unità sopra soglia | 231.586 |
| `M_min` nelle unità sopra soglia | 75.373 |
| `M_min` / non italiani nelle unità sopra soglia | 32,55% |
| `M_min` / studenti nelle unità sopra soglia | 13,89% |
| `M_min` / non italiani in tutte le unità analizzate | 9,89% |
| `M_min` / studenti in tutte le unità analizzate | 1,16% |

Le percentuali con suffisso `_sopra_30` usano come denominatore solo le unità sopra soglia; quelle con suffisso `_analizzati` usano tutte le unità del livello di aggregazione.

## File principali

- `data_raw/`: CSV MIM originali, inclusi i due flussi di anagrafe delle province autonome usati come possibile fallback di codice scuola.
- `data_processed/unita_202425.csv`: tutte le unità di base con `N`, `F`, `p`, flag sopra soglia e `M_min`.
- `data_processed/unita_sopra_30_202425.csv`: sole unità con `p > 0,30`.
- `results/aggregati_202425.csv`: aggregazioni per plesso, comune, provincia, regione e nazionale; contiene righe separate per `statale`, `paritaria` e `tutte`.
- `results/aggregati_nazionale_202425.csv`: estratto della riga nazionale combinata.
- `results/controlli_qualita_202425.csv`: conteggi di join, copertura e confronti con il flusso classi/studenti.
- `results/top_100_unita_sopra_30_202425.csv`: prime 100 unità ordinate per quota e `M_min`.
- `results/summary_202425.json`: riepilogo machine-readable.
- `metadata/fonti.csv`: URL di download, anno scolastico e data di riferimento dei file.
- `metadata/sha256_raw.csv`: hash SHA-256 dei file grezzi presenti al momento dell'elaborazione.

## Fonti e scelta dell'anno

Le fonti sono il [catalogo MIM — Studenti](https://dati.istruzione.it/opendata/opendata/catalogo/elements1/?area=Studenti) e il [catalogo MIM — Scuole](https://dati.istruzione.it/opendata/opendata/catalogo/elements1/?area=Scuole). I flussi studenti per cittadinanza e classi/studenti sono disponibili, al momento del download, fino all'a.s. 2024/25. Il catalogo anagrafe contiene anche aggiornamenti 2025/26 e 2026/27; per non mescolare anni scolastici diversi, il calcolo principale usa l'ultimo anno comune, 2024/25. Le copie anagrafiche statale e paritaria 2026/27 sono state scaricate e conservate per documentare l'ultimo aggiornamento, ma non entrano nel join principale.

Sono stati inclusi entrambi i tipi di gestione: statale e paritaria. Le anagrafiche standard sono unite alle anagrafiche `SCUANAAUT*` delle province autonome. Nei flussi studenti/classi utilizzati non risultano unità con codici provenienti dall'anagrafe autonoma; non sono quindi stati imputati valori alle province senza righe nei flussi studenti.

## Copertura e limiti

- I dataset `ALUITASTRACIT*` e `ALUCORSOINDCLA*` riguardano primaria, secondaria di primo grado e secondaria di secondo grado: la scuola dell'infanzia è esclusa perché non esiste una chiave comune comparabile a questo livello nei flussi usati.
- La metadatazione MIM dei flussi studenti/classi indica dati nazionali con esclusione delle province autonome di Trento e Bolzano. Aosta non produce righe nel flusso studenti scaricato; non è stata trasformata in zero.
- L'anagrafe statale/paritaria standard esclude Trento, Bolzano e Aosta; le anagrafiche autonome sono comunque state scaricate come controllo/fallback. Il risultato è quindi riferito alle unità effettivamente presenti nei flussi studenti e non pretende di stimare i territori mancanti.
- Le righe del flusso classi/studenti con `ANNOCORSOCLASSE = 7` rappresentano pluriclassi. Non sono assegnate artificialmente ai singoli anni di corso: per queste unità `classi_esatte` resta vuoto, mentre `N`, `F`, `p` e `M_min` vengono dal flusso per cittadinanza. Il controllo sui totali dell'intero flusso classi/studenti coincide con il totale del flusso cittadinanza.
- Su 134.784 unità di cittadinanza, 4.910 non hanno una chiave corso esatta nel flusso classi/studenti (4.868 statali e 42 paritarie); questo limita solo il campo accessorio sulle classi, non il calcolo del 30%.
- Il `M_min` è una somma di minimi locali, non un piano di assegnazione: non modella capienza, distanza, preferenze, fratelli, continuità didattica, né la disponibilità di unità riceventi. È un limite inferiore aritmetico sotto l'ipotesi richiesta di sostituzione uno-a-uno e `N` costante.

## Regole di calcolo

Per ogni unità:

- `N = ALUNNI` e `F = ALUNNICITTADINANZANONITALIANA` dal flusso MIM per cittadinanza;
- `p = F / N`;
- sopra soglia se `10 × F > 3 × N` (confronto esatto, quindi la soglia è strettamente `p > 0,30`);
- `M_min = max(0, ceil(F − 0,30 × N))`, implementato con aritmetica intera esatta per evitare problemi di arrotondamento binario.

La chiave di join con classi/studenti è `CodiceScuola + OrdineScuola + AnnoCorso` (`ANNOCORSOCLASSE` nel flusso classi); la chiave con l'anagrafe è `CodiceScuola`. Nessuna unità di cittadinanza è rimasta senza anagrafica nel run consegnato.

## Riproduzione

Dalla radice del progetto:

```bash
bash src/download_data.sh   # opzionale: riscarica i CSV MIM
bash src/run_analysis.sh
```

L'analisi usa la sola libreria standard di Python 3.10 o superiore. La data di generazione del run consegnato è 22 settembre 2026.
