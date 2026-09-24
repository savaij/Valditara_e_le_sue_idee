# Simulazione controfattuale del criterio del 30% — MIM a.s. 2024/25

Questo progetto calcola, come esercizio controfattuale, quante unità didattiche superano la soglia stretta del 30% di alunni con cittadinanza non italiana, quale sarebbe il minimo numero di riallocazioni necessario per riportarle alla soglia (senza applicare il criterio della conoscenza dell'italiano, che non è misurabile con questi dati), e — a partire da questa revisione — simula concretamente dove questi studenti potrebbero essere ricollocati e quanto lontano dovrebbero spostarsi.

## Aggiornamento di questa revisione

Il calcolo originario di `M_min` (`max(0, ceil(F − 0,30·N))`) è corretto **solo sotto l'ipotesi che ogni studente spostato venga sostituito da un altro studente**, mantenendo `N` costante — ipotesi esplicitata nella versione precedente di questo file ma in pratica poco realistica: una riallocazione non porta con sé un rimpiazzo automatico, quindi l'unità di partenza perde anche uno studente di N, non solo di F.

Sotto l'ipotesi corretta — **spostamento senza sostituzione, N diminuisce insieme a F** — il minimo `m` tale che `(F−m)/(N−m) ≤ 0,30` risolve `10F − 3N ≤ 7m`, cioè:

```
M_min = ceil(max(0, 10F − 3N) / 7)
```

invece di `ceil(max(0, F − 0,30·N))`. La differenza non è cosmetica: **a livello nazionale il numero corretto di spostamenti è 103.523, il 37,4% in più dei 75.373 calcolati con la formula precedente** (mantenuta come `m_min_con_sostituzione_legacy` per trasparenza — vedi `results/summary_202425.json`). La verifica è stata fatta anche per via numerica su 500.000 coppie casuali `(N, F)`, confermando che la nuova formula è sempre minima e sufficiente.

La correzione espone anche un caso limite genuino: **226 unità a livello nazionale hanno zero alunni con cittadinanza italiana** (`N = F`). In questi casi rimuovere solo alunni non italiani non cambia mai la quota (resta 100% finché resta almeno uno studente): sono matematicamente **irrisolvibili per pura sottrazione**, senza importare alunni italiani. Sono flaggate con `m_min_irrisolvibile = 1`, escluse dalle somme di `M_min` e dalla simulazione di spostamento (vedi sotto), e contate separatamente ovunque.

Questa revisione aggiunge inoltre una **simulazione realistica degli spostamenti** (`src/simulate_realloc.py`): per ogni studente da riallocare cerca la sede ricevente equivalente più vicina con posti disponibili, rispettandone capacità e soglia del 30%, e misura la distanza percorsa — si veda la sezione dedicata più sotto.

## Risultato nazionale sintetico

La granularità di base è:

`tipo di gestione × CodiceScuola (plesso) × OrdineScuola × AnnoCorso`.

Per il totale combinato statali + paritarie:

| Indicatore | Valore |
|---|---:|
| Unità analizzate | 134.784 |
| Unità con `p > 0,30` | 13.806 |
| — di cui irrisolvibili per pura sottrazione (`N = F`) | 226 |
| Studenti nelle unità sopra soglia | 542.790 |
| Alunni con cittadinanza non italiana nelle unità sopra soglia | 231.586 |
| `M_min` (senza sostituzione, unità irrisolvibili escluse) | **103.523** |
| `M_min_con_sostituzione` (formula legacy, N costante) | 75.373 |
| `M_min` / non italiani nelle unità sopra soglia | 44,70% |
| `M_min` / studenti nelle unità sopra soglia | 19,07% |
| `M_min` / non italiani in tutte le unità analizzate | 13,58% |
| `M_min` / studenti in tutte le unità analizzate | 1,59% |

Le percentuali con suffisso `_sopra_30` usano come denominatore solo le unità sopra soglia; quelle con suffisso `_analizzati` usano tutte le unità del livello di aggregazione. Cifre esatte in `results/summary_202425.json` e `results/aggregati_nazionale_202425.csv`.

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

Una destinazione può inoltre ricevere al più `floor((3N − 10F) / 7)` alunni non italiani aggiuntivi senza superare essa stessa la soglia del 30% (stessa aritmetica esatta usata per `M_min`); il tetto finale di posti ricevibili è il minimo tra capienza fisica e questo vincolo di soglia.

### Campionamento controfattuale (`--quota-campione`, default 0,20)

Il criterio del 30% MIM riguarda la **cittadinanza**, non la competenza linguistica. Poiché i dati non contengono alcuna misura di conoscenza dell'italiano, `--quota-campione` (default **0,20**) applica la simulazione di spostamento realistico solo a un sottoinsieme casuale — estratto con distribuzione Binomiale, seed fisso e riproducibile — degli studenti individuati da `M_min` per ciascuna unità sopra soglia, **come proxy puramente controfattuale** della quota che potrebbe non avere una conoscenza adeguata dell'italiano.

Non è una stima empirica della reale prevalenza di scarsa competenza linguistica: è un parametro di scenario, chiaramente distinto dai dati osservati (ogni riga di output riporta le colonne `quota_campione` e `seed`). Con `--quota-campione 1.0` si ottiene lo scenario "pieno" (tutto il pool `M_min`), usato come limite superiore di confronto.

Il campionamento è a livello di unità (non di singolo studente, che non è identificabile nei dati aggregati MIM): per ogni unità sopra soglia si estrae `Binomiale(M_min_unità, quota_campione)` con `numpy.random.default_rng(seed)`, iterando le unità nell'ordine deterministico con cui sono scritte in `unita_202425.csv`, cosicché il risultato non dipende da altri riordinamenti dello script.

### Algoritmo di assegnazione

Per ciascun gruppo `(tipo_gestione, ordine_scuola, anno_corso)`:

1. le unità di origine sono processate in ordine deterministico (quota di non italiani decrescente, poi codice_scuola) — priorità alle unità più sopra soglia;
2. per ciascuna unità, si cercano le destinazioni con posti disponibili più vicine tramite una griglia spaziale a celle di 0,25° con ricerca ad anelli crescenti, poi si calcola la distanza geodetica esatta (formula haversine, Terra come sfera, coordinate dal file di geocoding già presente nel progetto — copertura 100% dei plessi);
3. gli studenti campionati vengono assegnati alle destinazioni più vicine finché la domanda è soddisfatta o la capacità disponibile nel gruppo nazionale è esaurita (il residuo è marcato "non riallocabile");
4. le capacità delle destinazioni si aggiornano progressivamente: unità di origine vicine competono per gli stessi posti; chi viene processato prima (per severità) ha priorità. È quindi un'euristica greedy, non un ottimo globale.

La distanza riportata è quella **geodetica in linea d'aria**, non la distanza stradale reale: è un limite noto, dichiarato nei risultati (la distanza stradale/di percorrenza reale sarebbe sistematicamente maggiore, specie in territori collinari o insulari).

### Risultati della simulazione (seed 42)

| | Scenario default (20%) | Scenario completo (100%) |
|---|---:|---:|
| Studenti campionati | 20.689 | 103.523 |
| Studenti riallocati | 20.689 (100%) | 103.523 (100%) |
| Studenti non riallocabili | 0 | 0 |
| Distanza media | 2,40 km | 5,90 km |
| Distanza mediana | 1,63 km | 3,49 km |
| Distanza p90 | 5,55 km | 13,39 km |
| Distanza p95 | 7,62 km | 19,29 km |
| Distanza massima | 36,37 km | 80,58 km |

Con le ipotesi di capacità adottate (percentile 95° empirico), il pool nazionale di sedi riceventi candidate (106.606 unità) è ampio rispetto alla domanda anche nello scenario completo: **tutti** gli studenti campionati risultano riallocabili in entrambi gli scenari, con distanze mediane dell'ordine di 1,6–3,5 km. Le code sono però informative: gli spostamenti più lunghi (fino a ~80 km nello scenario completo) si concentrano in aree dove **molte unità sopra soglia sono clusterizzate** (es. la provincia di Piacenza, dove nello scenario completo diverse unità esauriscono la capacità ricevente locale e vengono abbinate a plessi in Brianza, a 70-80 km) — un effetto di concentrazione geografica della quota di alunni non italiani che l'aggregato nazionale nasconde. Si vedano `results/simulazione_riepilogo_202425_q*.json` per la rottura completa per ordine di scuola e regione, e `results/simulazione_spostamenti_dettaglio_202425_q*.csv` per il dettaglio origine→destinazione.

**Questo risultato "tutto riallocabile" dipende interamente dalle ipotesi di capacità e sostituibilità sopra descritte**: è la lettura ottimistica compatibile con i dati disponibili, non una garanzia. In particolare non modella: continuità del percorso scolastico, preferenze familiari, fratelli nella stessa scuola, tempi di trasporto reali, disponibilità di trasporto pubblico/scolastico, tempistiche amministrative, né l'indirizzo di studio nella secondaria di II grado (vedi limiti sopra). Riducendo il percentile di capienza (`--capienza-percentile`) o imponendo un tetto di distanza realistico (`--max-km`) la quota di studenti non riallocabili aumenta: si veda la sezione "Riproduzione" per rieseguire con parametri diversi.

### Controlli di qualità della simulazione

Nelle simulazioni singole, `results/controlli_qualita_simulazione_202425_q*.csv` verifica per ogni run soglia del 30%, capacità, compatibilità di tipologia e bilancio degli studenti. Nel Monte Carlo gli stessi controlli sono inclusi nelle metriche per run e aggregati nel riepilogo.

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
- Con una singola simulazione (`src/simulate_realloc.py` o `bash src/run_simulation.sh`), i file `simulazione_spostamenti_dettaglio`, `simulazione_non_riallocabili`, `simulazione_riepilogo`, `simulazione_distribuzione_distanze` e `controlli_qualita_simulazione` vengono salvati in `results/` con suffisso `202425_q{Q}_seed{S}`. Il dettaglio CSV contiene le coppie origine→destinazione; il riepilogo JSON include metriche per ordine di scuola e regione.
- Con `bash src/run_simulation.sh --montecarlo N [SEED_BASE]`, il runner salva solo due file complessivi in `results/`: `simulazione_montecarlo_dettaglio_202425_nN_seedBASE-ULTIMO_ordcas.json` contiene le metriche di ogni run per entrambe le quote (20% e 100%); `simulazione_montecarlo_202425_nN_seedBASE-ULTIMO_ordcas.json` contiene media, deviazione standard, minimo e massimo per le metriche aggregate in ciascuno scenario.
- Per ispezionare gli spostamenti estremi del Monte Carlo, `python3 src/inspect_montecarlo_outliers.py` rilegge il JSON di dettaglio predefinito, riesegue i 10 run con massimo più alto sopra 500 km e salva le coppie origine→destinazione in un CSV con coordinate. Usare `--soglia-km 100` per abbassare la soglia, `--top-runs 0` per rieseguire tutti i run sopra soglia, oppure passare un altro JSON e/o `--output percorso.csv`.
- `metadata/fonti.csv`: URL di download, anno scolastico e data di riferimento dei file.
- `metadata/sha256_raw.csv`: hash SHA-256 dei file grezzi presenti al momento dell'elaborazione.

Nei nomi dei file della simulazione singola, `Q` e `S` codificano rispettivamente `quota_campione` (in percento, es. `q020` = 0,20) e `seed`.

## Fonti e scelta dell'anno

Le fonti sono il [catalogo MIM — Studenti](https://dati.istruzione.it/opendata/opendata/catalogo/elements1/?area=Studenti) e il [catalogo MIM — Scuole](https://dati.istruzione.it/opendata/opendata/catalogo/elements1/?area=Scuole). I flussi studenti per cittadinanza e classi/studenti sono disponibili, al momento del download, fino all'a.s. 2024/25. Il catalogo anagrafe contiene anche aggiornamenti 2025/26 e 2026/27; per non mescolare anni scolastici diversi, il calcolo principale usa l'ultimo anno comune, 2024/25. Le copie anagrafiche statale e paritaria 2026/27 sono state scaricate e conservate per documentare l'ultimo aggiornamento, ma non entrano nel join principale.

Sono stati inclusi entrambi i tipi di gestione: statale e paritaria. Le anagrafiche standard sono unite alle anagrafiche `SCUANAAUT*` delle province autonome. Nei flussi studenti/classi utilizzati non risultano unità con codici provenienti dall'anagrafe autonoma; non sono quindi stati imputati valori alle province senza righe nei flussi studenti.

## Copertura e limiti

- I dataset `ALUITASTRACIT*` e `ALUCORSOINDCLA*` riguardano primaria, secondaria di primo grado e secondaria di secondo grado: la scuola dell'infanzia è esclusa perché non esiste una chiave comune comparabile a questo livello nei flussi usati.
- La metadatazione MIM dei flussi studenti/classi indica dati nazionali con esclusione delle province autonome di Trento e Bolzano. Aosta non produce righe nel flusso studenti scaricato; non è stata trasformata in zero.
- L'anagrafe statale/paritaria standard esclude Trento, Bolzano e Aosta; le anagrafiche autonome sono comunque state scaricate come controllo/fallback. Il risultato è quindi riferito alle unità effettivamente presenti nei flussi studenti e non pretende di stimare i territori mancanti.
- Le righe del flusso classi/studenti con `ANNOCORSOCLASSE = 7` rappresentano pluriclassi. Non sono assegnate artificialmente ai singoli anni di corso: per queste unità `classi_esatte` resta vuoto, mentre `N`, `F`, `p` e `M_min` vengono dal flusso per cittadinanza. Il controllo sui totali dell'intero flusso classi/studenti coincide con il totale del flusso cittadinanza.
- Su 134.784 unità di cittadinanza, 4.910 non hanno una chiave corso esatta nel flusso classi/studenti (4.868 statali e 42 paritarie); questo limita il campo accessorio sulle classi (e quindi l'ammissibilità come destinazione nella simulazione), non il calcolo del 30% in sé.
- Il flusso MIM non contiene l'indirizzo di studio per la secondaria di II grado (liceo/tecnico/professionale e relative articolazioni): la simulazione tratta come equivalenti unità che nella realtà non lo sono sempre, per questo ordine di scuola. Vedi la sezione "Simulazione realistica degli spostamenti".
- `M_min` (senza sostituzione) è comunque un limite inferiore aritmetico per unità, non un piano di assegnazione completo: la simulazione (sezione precedente) tenta di colmare questo gap, ma resta un'euristica greedy con le ipotesi di capacità e campionamento dichiarate, non un modello di scelta scolastica reale (non modella preferenze, fratelli, continuità didattica, trasporto, tempistiche amministrative).
- 226 unità (statali + paritarie) hanno zero alunni italiani e sono matematicamente irrisolvibili per pura sottrazione di alunni non italiani: sono escluse dalle somme di `M_min` e dalla simulazione, e riportate separatamente.

## Regole di calcolo

Per ogni unità:

- `N = ALUNNI` e `F = ALUNNICITTADINANZANONITALIANA` dal flusso MIM per cittadinanza;
- `p = F / N`;
- sopra soglia se `10 × F > 3 × N` (confronto esatto, quindi la soglia è strettamente `p > 0,30`);
- **`M_min = ceil(max(0, 10F − 3N) / 7)`** — minimo intero `m` tale che `(F−m)/(N−m) ≤ 0,30`, spostamento **senza sostituzione** (`N` diminuisce di `m`), aritmetica intera esatta. Se `N = F > 0` (zero alunni italiani), l'unità è flaggata `m_min_irrisolvibile = 1` e `M_min` resta vuoto: nessun `m` finito soddisfa il vincolo per pura sottrazione.
- `M_min_con_sostituzione_legacy = max(0, ceil(F − 0,30·N))` — formula della versione precedente di questo progetto, valida solo se ogni studente spostato è sostituito 1:1 mantenendo `N` costante; mantenuta per trasparenza/confronto, non usata come indicatore principale.

La chiave di join con classi/studenti è `CodiceScuola + OrdineScuola + AnnoCorso` (`ANNOCORSOCLASSE` nel flusso classi); la chiave con l'anagrafe è `CodiceScuola`. Nessuna unità di cittadinanza è rimasta senza anagrafica nel run consegnato.

## Riproduzione

Dalla radice del progetto:

```bash
bash src/download_data.sh    # opzionale: riscarica i CSV MIM
bash src/run_analysis.sh     # M_min per unità + aggregazioni (richiede pandas)
bash src/run_simulation.sh   # simulazione realistica: scenario 20% (default) + 100% (seed 42)
bash src/run_simulation.sh --montecarlo 500   # 500 seed per quota, due JSON complessivi
```

`run_analysis.sh` richiede **pandas** per leggere, unire e aggregare i dataset.
La simulazione usa inoltre **numpy** per il generatore casuale riproducibile e
il calcolo vettoriale delle distanze. Per installare entrambe le dipendenze:

```bash
pip install pandas numpy
```

Per rieseguire la simulazione con parametri diversi (quota di campionamento, seed, percentile di capienza, tetto di distanza):

```bash
python3 src/simulate_realloc.py --quota-campione 0.20 --seed 42
python3 src/simulate_realloc.py --quota-campione 1.00 --seed 42          # scenario completo
python3 src/simulate_realloc.py --quota-campione 0.20 --seed 7           # sensitività al seed
python3 src/simulate_realloc.py --quota-campione 0.20 --capienza-percentile 75   # capienza più prudente
python3 src/simulate_realloc.py --quota-campione 1.00 --max-km 30        # tetto di distanza realistico
```

La simulazione usa `MAX_LIMIT_PER_CLASS = None` in `src/simulate_realloc.py` per mantenere la stima empirica predefinita. La data di generazione del run consegnato è 22 settembre 2026.
