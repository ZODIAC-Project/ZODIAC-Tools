"""
RAG-Retrieval-Qualitätstest über alle eindeutigen (state, legalEntity, fundingPlan)-
Kombinationen, mit vier unterschiedlich detaillierten Query-Formulierungen pro
Kombination, plus einer Zufalls-Baseline zur Einordnung der absoluten Zahlen.

`businessSector` wurde per Homogenitäts-Check (group_customers.py) verifiziert:
100% der 80 Gruppen haben einen einzigen konsistenten businessSector-Wert, daher
sicher für Level 4 nutzbar, ohne die Ground Truth zu verfälschen.
`companySize`, `clientRole`, `district` sind NICHT homogen genug (0%, 1.2%, 12.5%)
und werden deshalb bewusst nicht verwendet.

Usage: python rag_retrieval_benchmark.py
"""

import json
from math import comb
import requests
from collections import defaultdict

RAG_BASE_URL = "http://localhost:30110"  # rag-service (purpose-aware); ggf. anpassen
COLLECTION = "customers"
EVAL_PURPOSE = "general"
TOP_K = 10

QUERY_LEVELS = ["level_1_minimal", "level_2_zwei_felder", "level_3_voll",
                "level_4_erweitert", "level_4b_kontrolle"]


def load_customers(n_results: int = 2000) -> list[dict]:
    response = requests.post(
        f"{RAG_BASE_URL}/collections/{COLLECTION}/query",
        json={
            "query_texts": ["Kundendaten"],
            "n_results": n_results,
            "purpose": EVAL_PURPOSE,
            "include": ["documents"],
        },
    )
    response.raise_for_status()
    documents = response.json()["documents"][0]
    return [json.loads(doc) for doc in documents]


def build_ground_truth(customers: list[dict]) -> dict[tuple, dict]:
    """Gruppiert Kunden nach (state, legalEntity, fundingPlan) und merkt sich
    zusätzlich businessSector (verifiziert homogen innerhalb jeder Gruppe,
    daher reicht ein beliebiges Gruppenmitglied als Quelle) sowie district
    (NICHT homogen — dient nur als Kontrollfeld ähnlicher Textlänge, um zu
    prüfen ob level_4's Verbesserung an businessSector selbst liegt oder
    einfach an der zusätzlichen Query-Länge; die Korrektheit von district
    für die Ground Truth spielt für diesen Zweck keine Rolle)."""
    groups: dict[tuple, dict] = defaultdict(
        lambda: {"ids": set(), "businessSector": None, "district": None}
    )
    for c in customers:
        key = (c["state"], c["legalEntity"], c["fundingPlan"])
        groups[key]["ids"].add(c["id"])
        groups[key]["businessSector"] = c["businessSector"]
        if groups[key]["district"] is None:
            groups[key]["district"] = c["district"]
    return dict(groups)


def make_queries(state: str, legal_entity: str, funding_plan: str,
                  business_sector: str, district: str) -> dict[str, str]:
    """Vier zunehmend detaillierte Formulierungen derselben Kombination, plus
    eine Kontroll-Variante (level_4b) gleicher Feldanzahl/ähnlicher Textlänge
    wie level_4, aber mit `district` statt `businessSector`. Zweck: trennen,
    ob level_4's Verbesserung an businessSector selbst liegt (Hypothese 1) oder
    einfach daran, dass die Query generell länger/textreicher ist (Hypothese 2).
    `district` ist bewusst gewählt, weil es NICHT homogen innerhalb der Gruppen
    ist — die Ground Truth bleibt trotzdem dieselbe Kunden-ID-Menge, es geht
    hier nur um den Effekt auf das Retrieval, nicht um inhaltliche Korrektheit.

    Bewusst nur textuelle/kategoriale Felder (numerische Felder wie personalAnzahl
    verschlechtern Embedding-Retrieval nachweislich, siehe frühere curl-Tests)."""
    return {
        "level_1_minimal": f"fundingPlan: {funding_plan}",
        "level_2_zwei_felder": f"state: {state}, fundingPlan: {funding_plan}",
        "level_3_voll": f"state: {state}, legalEntity: {legal_entity}, fundingPlan: {funding_plan}",
        "level_4_erweitert": (
            f"state: {state}, legalEntity: {legal_entity}, fundingPlan: {funding_plan}, "
            f"businessSector: {business_sector}"
        ),
        "level_4b_kontrolle": (
            f"state: {state}, legalEntity: {legal_entity}, fundingPlan: {funding_plan}, "
            f"district: {district}"
        ),
    }


def query_rag(query_text: str, n_results: int = TOP_K) -> list[dict]:
    response = requests.post(
        f"{RAG_BASE_URL}/collections/{COLLECTION}/query",
        json={
            "query_texts": [query_text],
            "n_results": n_results,
            "purpose": EVAL_PURPOSE,
            "include": ["documents"],
        },
    )
    if response.status_code == 422:
        print(f"Validation error für Query: {query_text!r}")
        print(response.json())
    response.raise_for_status()
    documents = response.json()["documents"][0]
    return [json.loads(doc) for doc in documents]


def expected_hit_at_k_random(group_size: int, total: int, k: int = TOP_K) -> float:
    """Wahrscheinlichkeit, dass eine rein zufällige Ziehung von k aus total
    mindestens ein Mitglied der Gruppe (group_size) enthält (hypergeometrisch)."""
    if group_size >= total:
        return 1.0
    p_no_hit = comb(total - group_size, k) / comb(total, k)
    return 1 - p_no_hit


def evaluate_query(query_text: str, correct_ids: set[str], total_customers: int) -> dict:
    results = query_rag(query_text)
    returned_ids = [doc["id"] for doc in results]

    hits = [rid for rid in returned_ids if rid in correct_ids]
    first_hit_rank = next(
        (i + 1 for i, rid in enumerate(returned_ids) if rid in correct_ids),
        None,
    )

    return {
        "query": query_text,
        "hit_at_1": len(returned_ids) > 0 and returned_ids[0] in correct_ids,
        "hit_at_k": len(hits) > 0,
        "recall_at_k": len(hits) / len(correct_ids),
        "first_hit_rank": first_hit_rank,
        "random_baseline_hit_at_k": expected_hit_at_k_random(len(correct_ids), total_customers),
    }


def run_benchmark() -> dict[str, list[dict]]:
    print("Lade Kunden...")
    customers = load_customers()
    total_customers = len(customers)
    print(f"{total_customers} Kunden geladen.")

    ground_truth = build_ground_truth(customers)
    combinations = {k: v for k, v in ground_truth.items() if len(v["ids"]) > 0}
    print(f"{len(combinations)} Kombinationen gefunden.\n")

    results_by_level: dict[str, list[dict]] = {level: [] for level in QUERY_LEVELS}

    for i, (key, data) in enumerate(combinations.items(), start=1):
        state, legal_entity, funding_plan = key
        ids = data["ids"]
        queries = make_queries(state, legal_entity, funding_plan,
                                data["businessSector"], data["district"])

        print(f"[{i}/{len(combinations)}] {key} ({len(ids)} korrekte IDs)")
        for level, query_text in queries.items():
            result = evaluate_query(query_text, ids, total_customers)
            result["combination"] = key
            result["correct_count"] = len(ids)
            results_by_level[level].append(result)

            status = "HIT@1" if result["hit_at_1"] else ("HIT" if result["hit_at_k"] else "MISS")
            print(f"    {level:22s} {status:6s} recall={result['recall_at_k']:.2f} "
                  f"rank={result['first_hit_rank']} baseline={result['random_baseline_hit_at_k']:.1%}")

    return results_by_level


def summarize(results_by_level: dict[str, list[dict]]) -> None:
    print("\n" + "=" * 90)
    print(f"{'Level':22s} {'Hit@1':>8s} {'Hit@' + str(TOP_K):>8s} "
          f"{'Recall@' + str(TOP_K):>10s} {'MRR':>8s} {'Baseline':>10s} {'Delta':>8s}")
    print("-" * 90)

    for level in QUERY_LEVELS:
        results = results_by_level[level]
        n = len(results)
        hit_at_1 = sum(r["hit_at_1"] for r in results) / n
        hit_at_k = sum(r["hit_at_k"] for r in results) / n
        mean_recall = sum(r["recall_at_k"] for r in results) / n
        mrr = sum(1 / r["first_hit_rank"] for r in results if r["first_hit_rank"]) / n
        mean_baseline = sum(r["random_baseline_hit_at_k"] for r in results) / n
        delta = hit_at_k - mean_baseline

        print(f"{level:22s} {hit_at_1:8.1%} {hit_at_k:8.1%} {mean_recall:10.1%} "
              f"{mrr:8.3f} {mean_baseline:10.1%} {delta:+8.1%}")

    print("=" * 90)
    print("Delta = Hit@10 minus Zufalls-Baseline. Werte nahe 0% bedeuten: RAG liefert")
    print("kaum mehr Signal als zufälliges Ziehen von 10 Kunden aus allen 1000.")

    voll_misses = [r for r in results_by_level["level_4_erweitert"] if not r["hit_at_k"]]
    if voll_misses:
        print(f"\n{len(voll_misses)} komplette Misses bei level_4_erweitert:")
        for m in voll_misses:
            print(f"  {m['combination']} ({m['correct_count']} Kandidaten, "
                  f"Zufalls-Baseline={m['random_baseline_hit_at_k']:.1%})")


if __name__ == "__main__":
    results_by_level = run_benchmark()
    summarize(results_by_level)

    with open("rag_benchmark_results.json", "w", encoding="utf-8") as f:
        json.dump(results_by_level, f, ensure_ascii=False, indent=2, default=str)
    print("\nErgebnisse in rag_benchmark_results.json gespeichert.")