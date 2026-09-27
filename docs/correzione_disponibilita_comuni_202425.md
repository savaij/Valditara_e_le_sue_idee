# Correzione della disponibilità nei comuni — 27 settembre 2026

## Risultato

Con gli stessi dati e raggruppamenti del calcolo precedente, la correzione
di `src/check_change_comune.py` porta il numero di comuni con deficit di posti
interni da **2 a 808 su 5.270** (15,33%). Il deficit complessivo passa da
**2 a 12.485 studenti**. Sono coinvolti 1.169 gruppi scolastici distinti.

Questo è un deficit nello scenario modellato: per completare la riallocazione
servirebbero posti fuori comune oppure una modifica delle ipotesi. Il calcolo
non dimostra che tali posti esterni esistano, né misura trasferimenti imposti
dal decreto.

## Formula corretta

Per ciascuna unità (plesso, ordine scolastico, anno di corso), siano:

- `N`: studenti presenti;
- `F`: studenti con cittadinanza non italiana;
- `C`: capienza stimata, pari a 30 per il numero di classi.

I posti fisici liberi sono `P = max(0, C - N)`.
Inserendo `x` studenti non italiani, aumentano sia il numeratore sia il
denominatore della quota. Il vincolo è:

```text
(F + x) / (N + x) <= 3/10
10F + 10x <= 3N + 3x
7x <= 3N - 10F
H = floor((3N - 10F) / 7)

disponibilita_effettiva = max(0, min(P, H))
```

Il minimo applica entrambi i vincoli contemporaneamente. Il floor impedisce
di accogliere uno studente intero in più del consentito. L'aritmetica intera
evita errori di confronto alla soglia del 30%.
Le unità già sopra soglia hanno `H < 0` e disponibilità ricevibile zero.

Il vecchio calcolo usava invece:

```text
max(0, P - round((0.30*N - F) / 0.70))
```

Esempio: con `N = 20`, `F = 6`, `C = 30`, i posti fisici sono 10 ma
la quota è già esattamente il 30%. La disponibilità corretta è zero;
il vecchio calcolo assegnava dieci posti.
Quando una scuola era sopra soglia, sottrarre un limite negativo ne
aumentava artificiosamente la disponibilità. Nell'intero bacino il vecchio
calcolo attribuiva 99.816 posti ricevibili alle unità già sopra soglia;
il calcolo corretto ne attribuisce zero.

## Come si misura il deficit

Per ogni gruppo `(codice_comune, comune, provincia, ordine_scuola,
tipo_scuola_anagrafe)` si sommano:

- la domanda: `m_min` delle unità del gruppo;
- l'offerta: disponibilità effettiva delle unità del gruppo.

Il deficit del gruppo è `max(0, domanda - offerta)`. I deficit sono sommati
per comune e poi a livello complessivo. I posti di un altro comune o di
un'altra tipologia non compensano la carenza del gruppo.
Un comune può apparire in più righe del dettaglio ma è contato una sola
volta nel totale di 808.

La domanda complessiva è 25.927 studenti; 12.485 (48,15%) eccedono i posti
interni disponibili nei rispettivi gruppi. Pur essendo presenti molti posti
a livello nazionale, la loro localizzazione e compatibilità possono impedire
di utilizzarli per la domanda locale.

## I due comuni originari

| Comune e gruppo | Domanda | Posti prima | Posti corretti | Deficit prima | Deficit corretto |
|---|---:|---:|---:|---:|---:|
| Orte — primaria | 17 | 57 | 3 | 0 | 14 |
| Orte — superiore, tecnico commerciale e per geometri | 2 | 1 | 0 | 1 | 2 |
| Roccabianca — primaria | 1 | 10 | 0 | 0 | 1 |
| Roccabianca — secondaria I grado | 2 | 1 | 0 | 1 | 2 |

Il deficit totale di Orte passa da 1 a 16, quello di Roccabianca da 1 a 3.
A Orte il gruppo liceo scientifico ha 25 posti corretti disponibili, ma il
vincolo di tipologia li rende inutilizzabili per la domanda del tecnico.

## Presupposti mantenuti e limiti

- Dati MIM dell'a.s. 2024/25, non dell'anno scolastico 2026/27.
- Sole unità con `anno_corso == 1` e almeno dieci studenti.
- I filtri già presenti nell'analisi di base restano applicati, inclusa
  la caratteristica `NORMALE` per le statali.
- Capienza ipotetica di 30 studenti per classe; non è una misura dei posti
  fisicamente disponibili nelle scuole.
- Una classe imputata quando manca `classi_esatte` (71 unità nel bacino).
- Esclusione delle otto unità delle prime con soli studenti non italiani:
  la sola sottrazione non ne riduce la quota sotto il 30% finché restano
  studenti. Il bacino residuo comprende 5.270 comuni.
- Stessa tipologia anagrafica e stesso ordine scolastico. La gestione non è
  una chiave esplicita di questo script: il raggruppamento resta quello
  precedente e non coincide necessariamente con quello della simulazione.
- Intero pool `m_min`, senza campionamento al 34,6% e senza limite di 5 km.
- Nessuna ricerca di una destinazione concreta, né verifica della capacità
  fuori comune o dei tempi di viaggio.
- Dati aggregati per plesso e anno di corso: non si osserva la composizione
  delle singole sezioni, né nascita, percorso scolastico o competenza
  linguistica degli studenti.

I risultati descrivono un controfattuale sulla cittadinanza e sui vincoli
scelti. Per stimare l'applicazione del decreto occorrerebbero informazioni
sugli studenti effettivamente soggetti al limite e sulle capacità reali.
Questa correzione riguarda il calcolo comunale; non modifica la simulazione
geografica né risolve l'incoerenza del riepilogo nazionale tra numeratori
non filtrati e denominatori filtrati.

## File e riproduzione

- `results/comuni_cambio_comune_202425.csv`: dettaglio corretto dei 1.169
  gruppi con deficit, prodotto dallo script.
- `results/comuni_cambio_comune_202425_confronto.csv`: confronto tra vecchia
  e nuova formula sui gruppi con almeno un deficit prima o dopo.
- `results/comuni_cambio_comune_202425_riepilogo_comuni.csv`: elenco dei 808
  comuni, con deficit precedente e corretto e numero di gruppi coinvolti.

Da un ambiente Python con pandas installato, nella radice della repo:

```bash
python3 src/check_change_comune.py
```

Il comando rigenera il dettaglio corretto; i due file di confronto sono
istantanee del confronto con la formula precedente al commit di correzione.
L'opzione `--consenti-cambio-tipo-scuola` produce uno scenario diverso;
i risultati riportati qui sono quelli senza questa opzione.

## Verifiche eseguite

- Riprodotte esattamente le due righe del CSV precedente usando la vecchia
  formula sugli stessi dati.
- Confermati 808 comuni e 12.485 posti di deficit anche con un ricalcolo
  indipendente dei CSV.
- Per ogni unità ricevente, verificati disponibilità non negativa e intera,
  rispetto della capienza e della soglia dopo l'inserimento, e impossibilità
  di aggiungere un ulteriore studente senza violare almeno un vincolo.
- Verificata disponibilità zero per tutte le unità già sopra soglia.
