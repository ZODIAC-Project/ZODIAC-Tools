# RAG-Retrieval-Benchmark — Übersicht

## Ziel
Messen, wie gut die semantische Suche (`/collections/customers/query`) den
korrekten Kunden findet, wenn nur ein Teil seiner Felder als Suchtext
formuliert wird.

## Dateien

| Datei | Zweck |
|---|---|
| `unique_combinations.py` | Gruppiert alle Kunden nach `(state, legalEntity, fundingPlan)`, erzeugt `unique_combinations.json`. Prüft zusätzlich, welche weiteren Felder (`businessSector`, `companySize`, `clientRole`, `district`) innerhalb dieser Gruppen homogen genug sind, um gefahrlos in eine detailliertere Suchanfrage aufgenommen zu werden. |
| `test_rag.py` | Der eigentliche Benchmark: sendet für jede der 80 Kombinationen fünf zunehmend detaillierte Queries an RAG und misst Hit@1, Hit@10, Recall@10, MRR sowie eine Zufalls-Baseline zum Vergleich. |
| `rag_benchmark_results.json` | Rohergebnisse pro Query (wird beim Ausführen von `test_rag.py` erzeugt). |
| `unique_combinations.json` / `unique_combinations_extended.json` | Ground-Truth-Daten (Kombination → Liste korrekter IDs). |

## Ausführung
```bash
# 1. Homogenitäts-Check und Ground-Truth-Erzeugung
python3 group_customers.py

# 2. Benchmark laufen lassen (Port-Forward auf rag-service:30110 muss aktiv sein)
uv run python test_rag.py
```
## Query-Levels
| Level | Felder | Zweck |
|---|---|---|
| `level_1_minimal` | `fundingPlan` | Minimalinformation, viele Kunden teilen sich denselben Wert |
| `level_2_zwei_felder` | `state`, `fundingPlan` | |
| `level_3_voll` | `state`, `legalEntity`, `fundingPlan` | entspricht der ursprünglichen Gruppierung |
| `level_4_erweitert` | + `businessSector` | einziges Zusatzfeld, das in **100 %** der 80 Gruppen homogen ist |

**Bewusst ausgeschlossen:**
- Numerische Felder (`personalAnzahl`, `jahresUmsatz`) — führen nachweislich zu schlechterem Retrieval, da Embeddings keine Zahlenvergleiche abbilden können (empirisch verifiziert: Formulierungen mit "weniger als X Mitarbeitern" schnitten durchgängig schlechter ab als rein deskriptive Queries).
- `companySize` (0 % homogen), `clientRole` (1,2 %), `district` (12,5 %) — variieren innerhalb der 80 Gruppen zu stark; eine Query mit einem beliebigen Gruppenwert würde andere, eigentlich korrekte Kandidaten aktiv aus der Suche heraushebeln.

## Zufalls-Baseline
Da die 80 Gruppen unterschiedlich viele korrekte IDs enthalten (von
1000 Kunden), ist eine rohe Hit@10-Zahl allein nicht genug — eine
Gruppe mit 13 Kandidaten hat allein durch Zufall eine Trefferchance von
~11–12 % bei `top_k=10`. Das Skript berechnet diese hypergeometrische
Baseline pro Gruppe und zeigt zusätzlich **Delta = Hit@10 − Baseline** in der
Zusammenfassung. Ein Delta nahe 0 % bedeutet: RAG liefert kaum mehr Signal
als zufälliges Ziehen.

## Ergebnisse (alle vier Levels, inkl. Zufalls-Baseline)
```
==========================================================================================
Level                     Hit@1   Hit@10  Recall@10      MRR   Baseline    Delta
------------------------------------------------------------------------------------------
level_1_minimal            1.2%    10.0%       1.3%    0.037      11.9%    -1.9%
level_2_zwei_felder        2.5%    10.0%       1.4%    0.041      11.9%    -1.9%
level_3_voll               2.5%    13.8%       1.8%    0.055      11.9%    +1.9%
level_4_erweitert          6.2%    37.5%       4.3%    0.128      11.9%   +25.6%
level_4b_kontrolle         2.5%    13.8%       2.7%    0.055      11.9%    +1.9%
==========================================================================================
```

**Metriken:**
- **Hit@1**: Anteil der Queries, bei denen die korrekte ID an erster Stelle der Top-10-Ergebnisse steht.
- **Hit@10**: Anteil der Queries, bei denen die korrekte ID irgendwo in den Top-10-Ergebnissen steht.
- **Recall@10**: Anteil der korrekten IDs, die in den Top-10-Ergebnissen gefunden werden (für Gruppen mit mehreren korrekten IDs).
- **MRR**: Mean Reciprocal Rank — der Durchschnitt der Kehrwerte der Ränge der korrekten IDs in den Top-10-Ergebnissen (für Gruppen mit mehreren korrekten IDs).(Kurz: je höher, desto besser; 1.0 = immer an erster Stelle, 0.5 = im Durchschnitt an zweiter Stelle, 0.1 = im Durchschnitt an zehnter Stelle).
- **Baseline**: Erwartete Trefferquote bei rein zufälliger Auswahl von 10 IDs aus 1000 Kunden (hypergeometrische Verteilung, abhängig von der Anzahl korrekter IDs pro Gruppe). 