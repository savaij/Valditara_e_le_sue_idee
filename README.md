# Simulazione controfattuale del criterio del 30% — MIM a.s. 2024/25

## Correzione del calcolo dei posti disponibili nei comuni — 27 settembre 2026

Il calcolo di `src/check_change_comune.py` è stato corretto: i posti ricevibili
sono il **minimo** tra posti fisici e limite del 30%, con arrotondamento per
difetto. Con gli stessi dati, filtri e raggruppamenti del calcolo precedente,
i comuni con deficit interno passano da **2 a 808 su 5.270** e il deficit
complessivo da **2 a 12.485 studenti**. Si tratta di uno scenario sulle prime
del 2024/25 basato sulla cittadinanza, non di una stima degli obblighi reali
previsti dal decreto.

La [nota metodologica](docs/correzione_disponibilita_comuni_202425.md) spiega
la formula, il confronto, i presupposti, i limiti e come riprodurre il calcolo.
L'[elenco per comune](results/comuni_cambio_comune_202425_riepilogo_comuni.csv)
e il [confronto per gruppo scolastico](results/comuni_cambio_comune_202425_confronto.csv)
riportano il dettaglio. Le sezioni successive descrivono revisioni precedenti;
i loro numeri e parametri non descrivono necessariamente questo nuovo scenario.

Questo progetto calcola, come esercizio controfattuale, quante unità didattiche superano la soglia stretta del 30% di alunni stranieri non nati in Italia — usata come proxy di chi non conosce l'italiano, poiché la competenza linguistica non è misurabile con questi dati (i nati in Italia contano come italiani; vedi "Stima degli alunni non nati in Italia" più sotto) — quale sarebbe il minimo numero di riallocazioni necessario per riportarle alla soglia, e simula concretamente dove questi studenti potrebbero essere ricollocati e quanto lontano dovrebbero spostarsi.

## Aggiornamento di questa revisione

Il calcolo originario di `M_min` (`max(0, ceil(F − 0,30·N))`) è corretto **solo sotto l'ipotesi che ogni studente spostato venga sostituito da un altro studente**, mantenendo `N` costante — ipotesi esplicitata nella versione precedente di questo file ma in pratica poco realistica: una riallocazione non porta con sé un rimpiazzo automatico, quindi l'unità di partenza perde anche uno studente di N, non solo di F.

Sotto l'ipotesi corretta — **spostamento senza sostituzione, N diminuisce insieme a F** — il minimo `m` tale che `(F−m)/(N−m) ≤ 0,30` risolve `10F − 3N ≤ 7m`, cioè:

```
M_min = ceil(max(0, 10F − 3N) / 7)
```

invece di `ceil(max(0, F − 0,30·N))`. La differenza non è cosmetica: **a livello nazionale il numero corretto di spostamenti è 894, il 15,4% in più dei 775 calcolati con la formula precedente** (mantenuta come `m_min_con_sostituzione_legacy` per trasparenza — vedi `results/summary_202425.json`). La verifica è stata fatta anche per via numerica su 500.000 coppie casuali `(N, F)`, confermando che la nuova formula è sempre minima e sufficiente.

La correzione espone anche un caso limite genuino: **30 unità a livello nazionale hanno zero alunni nati in Italia** (`N = F`, con `F = alunni_non_nati_in_Italia`, vedi sotto). In questi casi rimuovere solo alunni non nati in Italia non cambia mai la quota (resta 100% finché resta almeno uno studente): sono matematicamente **irrisolvibili per pura sottrazione**, senza importare alunni nati in Italia. Sono flaggate con `m_min_irrisolvibile = 1`, escluse dalle somme di `M_min` e dalla simulazione di spostamento (vedi sotto), e contate separatamente ovunque.

Questa revisione aggiunge inoltre una **simulazione realistica degli spostamenti** (`src/simulate_realloc.py`): per ogni studente da riallocare cerca la sede ricevente equivalente più vicina con posti disponibili, rispettandone capacità e soglia del 30%, e misura la distanza percorsa — si veda la sezione dedicata più sotto.

**Aggiornamento successivo**: la stima di `F` non usa più direttamente la cittadinanza (`alunni_non_italiani`), ma `alunni_non_nati_in_Italia` come proxy di chi non conosce l'italiano — vedi "Stima degli alunni non nati in Italia" più sotto. I numeri di questa sezione e della tabella successiva riflettono già questa stima.

## Risultato nazionale sintetico

La granularità di base è:

`tipo di gestione × CodiceScuola (plesso) × OrdineScuola × AnnoCorso`.

Per il totale combinato statali + paritarie:

| Indicatore | Valore |
|---|---:|
| Unità analizzate | 115.454 |
| Unità con `p > 0,30` | 517 |
| — di cui irrisolvibili per pura sottrazione (`N = F`) | 30 |
| Studenti nelle unità sopra soglia | 4.998 |
| Alunni con cittadinanza non italiana nelle unità sopra soglia | 3.669 |
| Alunni non nati in Italia nelle unità sopra soglia (`F`, stima) | 1.945 |
| `M_min` (senza sostituzione, unità irrisolvibili escluse) | **894** |
| `M_min_con_sostituzione` (formula legacy, N costante) | 775 |
| `M_min` / non nati in Italia nelle unità sopra soglia | 45,96% |
| `M_min` / studenti nelle unità sopra soglia | 17,89% |
| `M_min` / non nati in Italia in tutte le unità analizzate | 0,33% |
| `M_min` / studenti in tutte le unità analizzate | 0,014% |

Le percentuali con suffisso `_sopra_30` usano come denominatore solo le unità sopra soglia; quelle con suffisso `_analizzati` usano tutte le unità del livello di aggregazione. `F` (alunni non nati in Italia) è una stima per unità — vedi "Stima degli alunni non nati in Italia" più sotto — non una misura osservata come `alunni_non_italiani` (cittadinanza). Cifre esatte in `results/summary_202425.json`, calcolato su `data_processed/unita_sopra_30_202425.csv` (tutte le unità con `p > 0,30`, senza soglia minima di alunni). `results/aggregati_202425.csv` e `results/aggregati_nazionale_202425.csv` sono invece calcolati solo sulle unità con almeno 10 alunni totali (la stessa soglia minima usata dalla simulazione, sezione successiva, e da `check_change_comune.py`): per questo il loro conteggio di unità sopra soglia (150) e `M_min` (512) sono più bassi.

## Simulazione realistica degli spostamenti

`src/simulate_realloc.py` estende il calcolo aritmetico di `M_min` con un tentativo di collocazione concreta: per ogni studente da riallocare cerca una sede ricevente realmente equivalente con posti disponibili, senza far superare a quella sede il 30%, e calcola la distanza geografica implicata. Non è un piano di assegnazione ottimale (richiederebbe un problema di trasporto a costo minimo): è un'euristica greedy deterministica, trasparente e riproducibile — vedi il docstring dello script per i dettagli.

### Cosa si intende per "unità equivalente"

Una destinazione è candidata per uno studente spostato da un'unità se e solo se:

- **stesso `tipo_gestione`** (statale↔statale, paritaria↔paritaria): un ricollocamento amministrativo tra scuola statale e paritaria non è realistico (iscrizione, retta, gestione differenti). Disattivabile con `--consenti-cambio-gestione` come verifica di sensitività, non di default.
- **stesso `ordine_scuola`** (primaria / secondaria I grado / secondaria II grado).
- **stesso `anno_corso`**: per continuità didattica, non si sposta un alunno di un anno di corso in un anno diverso.
- **codice_scuola diverso dall'origine** (per costruzione: un'unità sopra soglia non può essere anche destinazione, perché la destinazione deve avere `p ≤ 0,30`).

**Limite importante sui dati**: i flussi MIM usati (`ALUCORSOINDCLA`, `ALUITASTRACIT`) non contengono l'indirizzo di studio (es. liceo scientifico vs istituto tecnico economico) per la secondaria di II grado. La nozione di "equivalente" per la secondaria di II grado è quindi più larga di quella reale: nella simulazione un alunno di un liceo può in teoria essere abbinato a un istituto professionale dello stesso anno di corso, se è la sede libera più vicina. Non è un'omissione di modellazione, ma un limite dei dati open MIM disponibili a questa granularità.

### Capacità delle sedi riceventi

Non esiste nei dati un campo di capienza massima per plesso/classe. Si stima una capienza per classe empirica come percentile (default: **95°**, parametro `--capienza-percentile`) della distribuzione nazionale di alunni/classe osservata per ciascuna coppia `(tipo_gestione, ordine_scuola)`, tra le unità con chiave classi/studenti confrontabile (vedi `data_processed/capienza_classe_stimata_202425.csv`):

| Gestione | Ordine | Capienza stimata (P95) | Osservazioni |
|---|---|---:|---:|
| statale | primaria | 24,0 | 64.929 |
| statale | secondaria I grado | 24,0 | 21.178 |
| statale | secondaria II grado | 26,0 | 28.818 |
| paritaria | primaria | 26,0 | 6.272 |
| paritaria | secondaria I grado | 28,0 | 1.788 |
| paritaria | secondaria II grado | 29,0 | 6.889 |

La capienza stimata di un'unità è `classi_esatte × capienza_classe_stimata`; i posti fisici disponibili sono `max(0, capienza stimata − alunni_totali)`. Le unità senza `classi_esatte` (~3,6% del totale, vedi "Copertura e limiti") sono escluse dal pool di destinazioni: non è possibile stimarne la capacità, quindi per prudenza non vengono usate come riceventi (possono comunque restare unità di origine).

In `src/simulate_realloc.py`, `MAX_LIMIT_PER_CLASS` può essere impostata a un intero positivo: in quel caso sostituisce il percentile empirico come capienza massima per classe. Con il valore predefinito `None` resta attiva la stima al percentile configurato da `--capienza-percentile`.

Una destinazione può inoltre ricevere al più `floor((3N − 10F) / 7)` alunni non nati in Italia aggiuntivi senza superare essa stessa la soglia del 30% (stessa aritmetica esatta usata per `M_min`, con `F = alunni_non_nati_in_Italia`); il tetto finale di posti ricevibili è il minimo tra capienza fisica e questo vincolo di soglia.

### Stima degli alunni non nati in Italia (proxy della competenza linguistica)

Il criterio del 30% MIM riguarda la **cittadinanza**, non la competenza linguistica, e i dati non contengono alcuna misura diretta della conoscenza dell'italiano. Invece di campionare una quota arbitraria del pool `M_min`, la stima di chi non conosce l'italiano è ora fatta **a monte, in `analyze.py`**, per ciascuna unità:

```
alunni_non_nati_in_Italia = round_half_up(alunni_non_italiani × (100 − per100) / 100)
```

dove `per100` è la quota di alunni stranieri **nati in Italia** ogni 100 alunni stranieri, per `(regione, ordine di scuola)`, dalla distribuzione di riferimento MIM 2022/23 (`distribuzioni_di_riferimento/alunni_cittadinanza_non_italiana_nati_in_italia_2022_2023.csv`; colonne `primaria_per100`, `secondaria_I_per100`, `secondaria_II_per100`). L'arrotondamento è per unità, allo 0,5 verso l'alto (`round_half_up`), su aritmetica intera esatta (niente errori di virgola mobile, dato che `per100` ha un solo decimale).

Gli stranieri nati in Italia contano come italiani a tutti gli effetti: `alunni_nati_in_Italia = alunni_totali − alunni_non_nati_in_Italia`. `sopra_30`, `m_min` e tutta la simulazione di spostamento sono calcolati su `alunni_non_nati_in_Italia`, non più sulla sola cittadinanza (`alunni_italiani`/`alunni_non_italiani` restano disponibili come conteggi per cittadinanza, invariati). Non è una stima empirica della reale prevalenza di scarsa competenza linguistica: è una proxy regionale su dati di riferimento esterni, chiaramente distinta dai dati osservati (colonne `quota_non_nati_in_Italia_riferimento` e `alunni_non_nati_in_Italia` in `unita_202425.csv`).

`src/simulate_realloc.py` non applica più alcun campionamento: **ogni unità sopra soglia rialloca esattamente il proprio `m_min`** così calcolato. Il parametro `--seed` resta, ma serve solo per `--ordine-origine-casuale` (vedi sotto); non esiste più una quota di scenario da passare via riga di comando.

### Algoritmo di assegnazione

Per ciascun gruppo `(tipo_gestione, ordine_scuola, anno_corso)`:

1. le unità di origine sono processate in ordine deterministico (quota di non nati in Italia decrescente, poi codice_scuola) — priorità alle unità più sopra soglia;
2. per ciascuna unità, si cercano le destinazioni con posti disponibili più vicine tramite una griglia spaziale a celle di 0,25° con ricerca ad anelli crescenti, poi si calcola la distanza geodetica esatta (formula haversine, Terra come sfera, coordinate dal file di geocoding già presente nel progetto — copertura 100% dei plessi);
3. gli studenti da riallocare (tutto `m_min` dell'unità) vengono assegnati alle destinazioni più vicine finché la domanda è soddisfatta o la capacità disponibile nel gruppo nazionale è esaurita (il residuo è marcato "non riallocabile");
4. le capacità delle destinazioni si aggiornano progressivamente: unità di origine vicine competono per gli stessi posti; chi viene processato prima (per severità) ha priorità. È quindi un'euristica greedy, non un ottimo globale.

La distanza riportata è quella **geodetica in linea d'aria**, non la distanza stradale reale: è un limite noto, dichiarato nei risultati (la distanza stradale/di percorrenza reale sarebbe sistematicamente maggiore, specie in territori collinari o insulari).

### Risultati della simulazione (seed 42)

La simulazione opera sulle sole unità con `anno_corso == 1` (vedi `data_processed/unita_202425.csv` filtrato in `simulate_realloc.py`), un sottoinsieme delle unità analizzate da `analyze.py`; per questo i totali qui sotto (da `results/simulazione_riepilogo_202425_seed42.json`) non coincidono con la tabella nazionale sopra, che copre tutti gli anni di corso.

| Indicatore | Valore |
|---|---:|
| Unità sopra soglia in simulazione | 50 |
| Unità di destinazione candidate | 25.368 |
| Studenti da riallocare (`m_min`, nessun campionamento) | 150 |
| Studenti riallocati | 150 (100%) |
| Studenti non riallocabili | 0 |
| Distanza media | 7,68 km |
| Distanza mediana | 6,59 km |
| Distanza p90 | 15,68 km |
| Distanza p95 | 22,01 km |
| Distanza massima | 39,42 km |

Con le ipotesi di capacità adottate (limite esplicito di 30 alunni/classe, `MAX_LIMIT_PER_CLASS`), il pool nazionale di sedi riceventi candidate è ampio rispetto alla domanda: **tutti e 150** gli studenti da riallocare risultano collocabili, con distanza mediana di 6,6 km. Le code sono comunque informative: gli spostamenti più lunghi (fino a ~39 km) si concentrano in regioni dove le unità sopra soglia sono poche e sparse (es. Basilicata, dove la mediana supera i 30 km) — un effetto di concentrazione geografica che l'aggregato nazionale nasconde. Si veda `results/simulazione_riepilogo_202425_seed42.json` per la rottura completa per ordine di scuola e regione, e `results/simulazione_spostamenti_dettaglio_202425_seed42.csv` per il dettaglio origine→destinazione.

**Questo risultato "tutto riallocabile" dipende interamente dalle ipotesi di capacità e sostituibilità sopra descritte**: è la lettura ottimistica compatibile con i dati disponibili, non una garanzia. In particolare non modella: continuità del percorso scolastico, preferenze familiari, fratelli nella stessa scuola, tempi di trasporto reali, disponibilità di trasporto pubblico/scolastico, tempistiche amministrative, né l'indirizzo di studio nella secondaria di II grado (vedi limiti sopra). Riducendo il percentile di capienza (`--capienza-percentile`, se `MAX_LIMIT_PER_CLASS` è disattivato) o imponendo un tetto di distanza realistico (`--max-km`) la quota di studenti non riallocabili aumenta: si veda la sezione "Riproduzione" per rieseguire con parametri diversi.

### Controlli di qualità della simulazione

Nelle simulazioni singole, `results/controlli_qualita_simulazione_202425_seed{S}.csv` verifica per ogni run soglia del 30%, capacità, compatibilità di tipologia e bilancio degli studenti. Nel Monte Carlo gli stessi controlli sono inclusi nelle metriche per run e aggregati nel riepilogo.

## File principali

- `data_raw/`: CSV MIM originali, inclusi i due flussi di anagrafe delle province autonome usati come possibile fallback di codice scuola. Non versionato (si riscarica con `src/download_data.sh`).
- `data_processed/unita_202425.csv`: tutte le unità di base con `N`, `F`, `p`, flag sopra soglia, `M_min` (senza sostituzione), flag di irrisolvibilità e `M_min` legacy. Rigenerato da `analyze.py`, non versionato (grande, rigenerabile in pochi secondi).
- `data_processed/unita_sopra_30_202425.csv`: sole unità con `p > 0,30`. Idem, non versionato.
- `data_processed/geocoding_scuole_202425.csv` e `geocoding_cache.json`: coordinate geocodificate di tutti i plessi (100% di copertura), versionate perché costose da rigenerare (richiedono chiamate a pagamento a Google Geocoding API).
- `data_processed/capienza_classe_stimata_202425.csv`: capienza massima per classe stimata (percentile empirico) per `(tipo_gestione, ordine_scuola)`, usata dalla simulazione.
- `results/aggregati_202425.csv`: aggregazioni per plesso, comune, provincia, regione e nazionale; contiene righe separate per `statale`, `paritaria` e `tutte`.
- `results/aggregati_nazionale_202425.csv`: estratto della riga nazionale combinata.
- `results/controlli_qualita_202425.csv`: conteggi di join, copertura e confronti con il flusso classi/studenti.
- `results/top_100_unita_sopra_30_202425.csv`: prime 100 unità ordinate per quota e `M_min`.
- `results/summary_202425.json`: riepilogo machine-readable del calcolo `M_min`.
- `results/mappa_scuole_202425.html`: mappa interattiva dei plessi con `m_min_sopra_30 > 0` (generata da `src/plot_schools.py`).
- Con una singola simulazione (`src/simulate_realloc.py` o `bash src/run_simulation.sh`), i file `simulazione_spostamenti_dettaglio`, `simulazione_non_riallocabili`, `simulazione_riepilogo`, `simulazione_distribuzione_distanze` e `controlli_qualita_simulazione` vengono salvati in `results/` con suffisso `202425_seed{S}` (`S` = seed; con `--ordine-origine-casuale` il suffisso diventa `202425_seed{S}_ordcas`). Il dettaglio CSV contiene le coppie origine→destinazione; il riepilogo JSON include metriche per ordine di scuola e regione.
- Con `bash src/run_simulation.sh --montecarlo N [SEED_BASE]`, il runner salva solo due file complessivi in `results/`: `simulazione_montecarlo_dettaglio_202425_nN_seedBASE-ULTIMO_ordcas.json` contiene le metriche di ogni run; `simulazione_montecarlo_202425_nN_seedBASE-ULTIMO_ordcas.json` contiene media, deviazione standard, minimo e massimo per le metriche aggregate su tutti i run. Non c'è più una dimensione di quota: ogni run rialloca esattamente `m_min` per unità, e la variabilità tra run viene solo dall'ordine casuale delle unità di origine.
- Per ispezionare gli spostamenti estremi del Monte Carlo, `python3 src/inspect_montecarlo_outliers.py` rilegge il JSON di dettaglio predefinito, riesegue i 10 run con massimo più alto sopra 500 km e salva le coppie origine→destinazione in un CSV con coordinate. Usare `--soglia-km 100` per abbassare la soglia, `--top-runs 0` per rieseguire tutti i run sopra soglia, oppure passare un altro JSON e/o `--output percorso.csv`.
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
- Sulle 115.454 unità di cittadinanza incluse nell'analisi (dopo il filtro `alunni_totali ≥ 10`), 499 non hanno una chiave corso esatta nel flusso classi/studenti; questo limita il campo accessorio sulle classi (e quindi l'ammissibilità come destinazione nella simulazione), non il calcolo del 30% in sé.
- Il flusso MIM non contiene l'indirizzo di studio per la secondaria di II grado (liceo/tecnico/professionale e relative articolazioni): la simulazione tratta come equivalenti unità che nella realtà non lo sono sempre, per questo ordine di scuola. Vedi la sezione "Simulazione realistica degli spostamenti".
- `M_min` (senza sostituzione) è comunque un limite inferiore aritmetico per unità, non un piano di assegnazione completo: la simulazione (sezione precedente) tenta di colmare questo gap, ma resta un'euristica greedy con le ipotesi di capacità e campionamento dichiarate, non un modello di scelta scolastica reale (non modella preferenze, fratelli, continuità didattica, trasporto, tempistiche amministrative).
- 30 unità (statali + paritarie, tra quelle sopra soglia) hanno zero alunni nati in Italia (`N = F`) e sono matematicamente irrisolvibili per pura sottrazione di alunni non nati in Italia: sono escluse dalle somme di `M_min` e dalla simulazione, e riportate separatamente.

## Regole di calcolo

Per ogni unità:

- `N = ALUNNI` dal flusso MIM per cittadinanza e `F = alunni_non_nati_in_Italia`, la stima per unità descritta in "Stima degli alunni non nati in Italia" più sotto (`alunni_non_italiani` per cittadinanza rimane disponibile come colonna separata, ma non è più la base di `p`, `sopra_30` e `M_min`);
- `p = F / N`;
- sopra soglia se `10 × F > 3 × N` (confronto esatto, quindi la soglia è strettamente `p > 0,30`);
- **`M_min = ceil(max(0, 10F − 3N) / 7)`** — minimo intero `m` tale che `(F−m)/(N−m) ≤ 0,30`, spostamento **senza sostituzione** (`N` diminuisce di `m`), aritmetica intera esatta. Se `N = F > 0` (zero alunni nati in Italia), l'unità è flaggata `m_min_irrisolvibile = 1` e `M_min` resta vuoto: nessun `m` finito soddisfa il vincolo per pura sottrazione.
- `M_min_con_sostituzione_legacy = max(0, ceil(F − 0,30·N))` — formula della versione precedente di questo progetto, valida solo se ogni studente spostato è sostituito 1:1 mantenendo `N` costante; mantenuta per trasparenza/confronto, non usata come indicatore principale.

La chiave di join con classi/studenti è `CodiceScuola + OrdineScuola + AnnoCorso` (`ANNOCORSOCLASSE` nel flusso classi); la chiave con l'anagrafe è `CodiceScuola`. Nessuna unità di cittadinanza è rimasta senza anagrafica nel run consegnato.

## Riproduzione

Dalla radice del progetto:

```bash
bash src/download_data.sh    # opzionale: riscarica i CSV MIM
bash src/run_analysis.sh     # M_min per unità + aggregazioni (richiede pandas)
bash src/run_simulation.sh   # simulazione realistica, run singola (default seed 42)
bash src/run_simulation.sh --montecarlo 500   # 500 seed, due JSON complessivi (Monte Carlo)
```

`run_analysis.sh` richiede **pandas** per leggere, unire e aggregare i dataset.
La simulazione usa inoltre **numpy** per il generatore casuale riproducibile e
il calcolo vettoriale delle distanze. Per installare entrambe le dipendenze:

```bash
pip install pandas numpy
```

Per rieseguire la simulazione con parametri diversi (seed, ordine casuale delle unità di origine, percentile di capienza, tetto di distanza):

```bash
python3 src/simulate_realloc.py --seed 42
python3 src/simulate_realloc.py --seed 7                                  # sensitività al seed (con --ordine-origine-casuale)
python3 src/simulate_realloc.py --seed 42 --ordine-origine-casuale        # ordine di origine casuale invece che deterministico
python3 src/simulate_realloc.py --seed 42 --capienza-percentile 75        # capienza più prudente (richiede MAX_LIMIT_PER_CLASS = None)
python3 src/simulate_realloc.py --seed 42 --max-km 30                     # tetto di distanza realistico
```

Nel run consegnato `src/simulate_realloc.py` usa il valore predefinito `MAX_LIMIT_PER_CLASS = 30` (limite esplicito di alunni per classe); impostarlo a `None` nello script attiva invece la stima empirica al percentile configurato da `--capienza-percentile`. La data di generazione del run consegnato è 28 settembre 2026.
