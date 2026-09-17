import json
from collections import defaultdict
from itertools import combinations as itertools_combinations

with open('customers.json', 'r', encoding='utf-8') as file:
    kunden = json.load(file)


# ---------------------------------------------------------------------------
# 2. Gruppierung über eine beliebige Feld-Liste 
# ---------------------------------------------------------------------------
def group_by_fields(kunden: list[dict], fields: list[str]) -> dict[tuple, list[str]]:
    grouped = defaultdict(list)
    for kunde in kunden:
        key = tuple(kunde.get(f) for f in fields)
        grouped[key].append(kunde['id'])
    return dict(grouped)


def save_grouping(grouped: dict[tuple, list[str]], fields: list[str], path: str) -> None:
    output = []
    for key, ids in grouped.items():
        entry = dict(zip(fields, key))
        entry["ids"] = ids
        output.append(entry)
    with open(path, 'w', encoding='utf-8') as file:
        json.dump(output, file, indent=2, ensure_ascii=False)
    print(f"{len(output)} einzigartige Kombinationen über {fields} → {path}")


# ---------------------------------------------------------------------------
# 3. Homogenitäts-Check: Bevor ein zusätzliches Feld (z.B. businessSector) in
#    eine Query aufgenommen wird, muss geprüft werden, ob es innerhalb der
#    bestehenden (state, legalEntity, fundingPlan)-Gruppen überhaupt konstant
#    ist. Ist es das nicht, würde die Query mit einem beliebigen Gruppenwert
#    andere, eigentlich korrekte Gruppenmitglieder aktiv aus der Suche
#    heraushebeln (siehe Diskussion zu Level 4).
# ---------------------------------------------------------------------------
def check_field_homogeneity(kunden: list[dict], base_fields: list[str],
                             candidate_field: str) -> dict:
    """Für jede base_fields-Gruppe: wie viele unterschiedliche Werte hat
    candidate_field innerhalb dieser Gruppe? homogen = genau 1."""
    grouped = defaultdict(set)
    for kunde in kunden:
        key = tuple(kunde.get(f) for f in base_fields)
        grouped[key].add(kunde.get(candidate_field))

    n_total = len(grouped)
    n_homogeneous = sum(1 for values in grouped.values() if len(values) == 1)
    return {
        "field": candidate_field,
        "total_groups": n_total,
        "homogeneous_groups": n_homogeneous,
        "homogeneous_ratio": n_homogeneous / n_total if n_total else 0.0,
        "non_homogeneous_examples": [
            (key, sorted(v)) for key, v in grouped.items() if len(v) > 1
        ][:5],  # nur ein paar Beispiele zur Illustration
    }


# ---------------------------------------------------------------------------
# 4. Ausführung
# ---------------------------------------------------------------------------
BASE_FIELDS = ["state", "legalEntity", "fundingPlan"]

# 4a. Bestehende 3-Felder-Gruppierung (unverändert zum Original)
grouped_3 = group_by_fields(kunden, BASE_FIELDS)
save_grouping(grouped_3, BASE_FIELDS, "unique_combinations.json")

# 4b. Kandidatenfelder für Level 4 auf Homogenität innerhalb der 3er-Gruppen prüfen
CANDIDATE_FIELDS = ["businessSector", "companySize", "clientRole", "district"]

print("\n--- Homogenitäts-Check pro Kandidatenfeld ---")
for field in CANDIDATE_FIELDS:
    result = check_field_homogeneity(kunden, BASE_FIELDS, field)
    print(f"{field:15s} homogen in {result['homogeneous_groups']}/{result['total_groups']} "
          f"Gruppen ({result['homogeneous_ratio']:.1%})")
    if result["non_homogeneous_examples"]:
        print(f"  Beispiele für Abweichung: {result['non_homogeneous_examples'][:2]}")

# 4c. Nur mit Feldern erweitern, die tatsächlich hinreichend homogen sind
#     (Schwelle hier bewusst hoch gesetzt — 95%, damit "Level 4"-Queries nicht
#     versehentlich falsche Kandidaten ausschließen)
HOMOGENEITY_THRESHOLD = 0.95
usable_extra_fields = [
    field for field in CANDIDATE_FIELDS
    if check_field_homogeneity(kunden, BASE_FIELDS, field)["homogeneous_ratio"] >= HOMOGENEITY_THRESHOLD
]
print(f"\nFür Level 4 geeignete Zusatzfelder (>= {HOMOGENEITY_THRESHOLD:.0%} homogen): "
      f"{usable_extra_fields}")

# 4d. Falls gewünscht: erweiterte Gruppierung mit den zusätzlichen Feldern
#     zur Kontrolle/Doku speichern (führt zu mehr, kleineren Gruppen)
if usable_extra_fields:
    extended_fields = BASE_FIELDS + usable_extra_fields
    grouped_extended = group_by_fields(kunden, extended_fields)
    save_grouping(grouped_extended, extended_fields, "unique_combinations_extended.json")