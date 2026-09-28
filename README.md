# Il limite del 30% nelle scuole

Abbiamo usato i dati del Ministero dell'Istruzione per l'anno scolastico
2024/25 per capire dove la quota di studenti considerata nell'analisi supera
il 30% e cosa succederebbe cercando per loro un'altra scuola vicina.

I dati distinguono gli studenti per cittadinanza, ma non dicono per ciascuno
se è nato in Italia. Per stimarlo usiamo le quote pubblicate dal Ministero
per regione e grado scolastico nel 2022/23. I risultati sono quindi **stime**,
non il conteggio degli studenti che saranno coinvolti dal decreto.

Consideriamo le scuole statali ordinarie e le paritarie. Escludiamo i gruppi
con meno di 10 studenti. Un *gruppo* è formato dagli studenti dello stesso
anno di corso in una sede scolastica: può comprendere più classi.

## Che cosa emerge

Nel campione ci sono **115.454 gruppi**, frequentati da **6.250.109 studenti**.
Guardando tutti gli anni di corso, **150 gruppi** superano la soglia del 30%.
In questi gruppi stimiamo **1.471 studenti** considerati nel calcolo della
quota. Se si cercasse di riportare tutti i gruppi sotto soglia togliendo
studenti senza sostituirli, il minimo teorico sarebbe **512**.

Per simulare i cambi di scuola ci concentriamo invece sulle **prime classi**.
Qui i gruppi sopra soglia sono **50** e gli studenti stimati da riallocare
sono **150**. I 50 gruppi comprendono in tutto 67 classi, ma non sappiamo
quali singole classi superino il 30%: la quota è misurata sul gruppo.

La simulazione cerca per questi 150 studenti un posto in un'altra scuola
entro **5 km in linea d'aria**. Con una capienza ipotizzata di **30 studenti
per classe**, trova una destinazione per **78**; per gli altri **72** non ne
trova una con le regole scelte. Questo non vuol dire che nella realtà i 72
debbano cambiare comune o non possano trovare scuola.

Un controllo separato confronta domanda e posti stimati **all'interno di ogni
comune**, fra scuole dello stesso grado e dello stesso tipo registrato dal
Ministero. Trova **23 comuni su 5.272** con un deficit interno, per un totale
di **107 posti**. Questo controllo non usa il raggio di 5 km: un posto nel
comune vicino potrebbe essere più accessibile di uno nel proprio. I comuni e
i relativi deficit sono nel [file di dettaglio](results/comuni_cambio_comune_202425.csv).

## Le mappe

- [Tutti gli anni di corso](results/mappa_studenti_sopra_30_tutti_anni_202425.html): i numeri nei cerchi mostrano dove si concentrano i 1.471 studenti stimati nei gruppi sopra soglia.
- [Prime classi](results/mappa_studenti_da_riallocare_prime_202425.html): i numeri mostrano i 150 studenti stimati da riallocare. Spuntando «Solo non riallocabili entro 5 km» restano visibili soltanto le scuole con studenti per cui la simulazione non ha trovato una destinazione; i numeri nei cerchi indicano quanti sono.

Avvicinandosi si vedono le singole scuole. Allontanandosi, i cerchi vicini
si uniscono: il numero al centro è la somma degli studenti. I cerchi più
numerosi crescono un po', ma restano compatti. I punti di partenza sono le **scuole**, non le abitazioni
degli studenti. Le mappe
si possono aprire nel browser con una connessione internet per caricare la
cartografia di base.

## Come abbiamo fatto i calcoli

Per stimare i posti, consideriamo solo scuole dello stesso grado e anno di
corso, senza mescolare statali e paritarie. La ricerca entro 5 km usa la
distanza tra le sedi, non il tragitto da casa. Non disponiamo dei posti
effettivamente liberi, degli indirizzi degli studenti o della composizione
delle singole classi. Per questo i risultati descrivono **lo scenario scelto**,
non gli spostamenti che avverranno davvero.

I numeri completi sono nel [riepilogo nazionale](results/summary_202425.json),
nel [riepilogo della simulazione](results/simulazione_riepilogo_202425_seed42.json)
e nella [nota sul calcolo comunale](docs/correzione_disponibilita_comuni_202425.md).
Le fonti dei dati sono elencate in [metadata/fonti.csv](metadata/fonti.csv).

Per rigenerare i risultati servono i CSV originali in `data_raw/`, Python con
`pandas` e `numpy`, e questi comandi dalla cartella della repo:

```bash
bash src/run_analysis.sh
bash src/run_simulation.sh
python3 src/check_change_comune.py
python3 src/analysis_big_cities/plot_heatmaps.py
```
