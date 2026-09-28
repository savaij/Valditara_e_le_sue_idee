# Disponibilità interna ai comuni — scenario corrente

Il calcolo sulle sole prime classi dell'a.s. 2024/25, con gruppi di almeno
10 studenti, indica **23 comuni su 5.272** con deficit interno: **107 posti**
in **27 gruppi** comune × ordine di scuola × tipologia anagrafica.
Il dettaglio corrente è in
[`results/comuni_cambio_comune_202425.csv`](../results/comuni_cambio_comune_202425.csv).
I numeri di revisioni precedenti non sono applicabili a questo campione.

## Che cosa misura

Per ogni gruppo di plesso e anno di corso, `N` è il totale degli studenti e
`F` è la stima degli studenti considerati nel numeratore del 30%, costruita
in `analyze.py` a partire dalla cittadinanza e dalle quote regionali MIM dei
nati in Italia. Il minimo da rimuovere senza sostituzione è
`m_min = ceil(max(0, 10F − 3N)/7)`.

Una sede ricevente ha capienza ipotizzata `C = 30 × classi_esatte`; se il
numero delle classi manca, lo script imputa una classe. I posti fisici sono
`P = max(0, C − N)`. Accogliendo `x` studenti del numeratore, la quota diventa
`(F+x)/(N+x)`, dunque il tetto del 30% permette al massimo
`H = floor((3N − 10F)/7)` ulteriori ingressi. La disponibilità effettiva è
`max(0, min(P,H))`. Una sede già sopra il 30% non può ricevere studenti del
numeratore.

Si sommano domanda e disponibilità per **comune, ordine e tipologia**. Il
deficit di ogni gruppo è `max(0, domanda − disponibilità)`; un comune con
più gruppi in deficit viene contato una sola volta nei 23 comuni.

Questo calcolo non cerca una scuola concreta entro 5 km: è un indicatore
separato di capacità **all'interno dei confini comunali**. Una scuola in un
altro comune può essere più vicina di una nel proprio. I 107 posti non sono
quindi studenti certamente costretti a cambiare comune. La simulazione
geografica, descritta nel README, applica invece il raggio di 5 km tra
plessi e distingue i 150 studenti da riallocare dai 78 assegnati e dai 72
senza destinazione trovata.

## Limiti e riproduzione

La capienza di 30 è un'ipotesi, non il numero di posti effettivamente liberi.
La quota è stimata a livello di plesso/anno, non osservata per singola
sezione. La tipologia anagrafica può essere più stretta o più larga della
compatibilità didattica reale. Il calcolo esclude i gruppi sotto 10 studenti,
come le altre analisi correnti.

Da un ambiente con `pandas` installato, nella radice della repo:

```bash
python3 src/check_change_comune.py
```

L'opzione `--consenti-cambio-tipo-scuola` produce uno scenario diverso e
non è usata nel CSV corrente.
