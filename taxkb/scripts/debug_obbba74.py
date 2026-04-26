#!/usr/bin/env python3
"""
Diagnostic script for OBBBA-74.

Traces the ontology augment path to find why Pub 17 doesn't appear.
This needs NO database — it only uses the in-code ontology.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from taxkb.publications.ontology import get_ontology
from taxkb.agent.classifier import classify_query

QUERY = "If I financed a vehicle in 2024, can I claim the interest deduction in 2025?"

# ── Step 1: Query classification ──────────────────────────────────
meta = classify_query(QUERY)
print(f"=== QUERY CLASSIFIER ===")
print(f"  intent       : {meta.intent}")
print(f"  tax_year     : {meta.tax_year}")
print(f"  confidence   : {meta.confidence}")
print(f"  topic_tags   : {meta.topic_tags}")
print()

# ── Step 2: Ontology matching ─────────────────────────────────────
ontology = get_ontology()
query_lower = QUERY.lower()

print(f"=== ONTOLOGY find_by_query ===")
matched_topics = ontology.find_by_query(QUERY)
print(f"  Total matched topics: {len(matched_topics)}")
print()

# Show all matched topics with scores
print(f"=== ALL MATCHED TOPICS (with scores) ===")
scores = {}
for topic in ontology._topics.values():
    score = 0
    matching_terms = []
    for term in topic.key_terms:
        if term.lower() in query_lower:
            score += 1
            matching_terms.append(term)
    if topic.display_name.lower() in query_lower:
        score += 2
        matching_terms.append(f"[display_name: {topic.display_name}]")
    if score > 0:
        scores[topic.topic_id] = (score, matching_terms)

ranked = sorted(scores.keys(), key=lambda tid: scores[tid][0], reverse=True)
for i, tid in enumerate(ranked):
    score, terms = scores[tid]
    pubs = ontology.get_pub_numbers_for_topic(tid)
    marker = " <<<< TARGET" if tid == "obbba_vehicle_interest" else ""
    print(f"  #{i+1}: {tid} (score={score}, pubs={pubs}){marker}")
    print(f"       matched terms: {terms}")
print()

# ── Step 3: Simulate _augment_from_ontology ───────────────────────
# Using the nav_pubs from the eval failure: ['334', '550', '970']
nav_pubs_from_eval = ['334', '550', '970']

print(f"=== SIMULATE _augment_from_ontology ===")
print(f"  nav_pubs (scoped): {nav_pubs_from_eval}")
print()

augment_pubs = []
for topic in matched_topics[:7]:
    pubs_for_topic = ontology.get_pub_numbers_for_topic(topic.topic_id)
    added = []
    for pn in pubs_for_topic:
        if pn not in nav_pubs_from_eval and pn not in augment_pubs:
            augment_pubs.append(pn)
            added.append(pn)
    print(f"  Topic: {topic.topic_id} → pubs={pubs_for_topic} → added={added}")
    print(f"    augment_pubs so far: {augment_pubs}")

print()
print(f"  Final augment_pubs[:6]: {augment_pubs[:6]}")
print(f"  '17' in augment_pubs[:6]? {'17' in augment_pubs[:6]}")
print()

# ── Step 4: Where is obbba_vehicle_interest ranked? ───────────────
obbba_rank = None
for i, t in enumerate(matched_topics):
    if t.topic_id == "obbba_vehicle_interest":
        obbba_rank = i
        break

if obbba_rank is not None:
    print(f"=== obbba_vehicle_interest RANK: #{obbba_rank + 1} of {len(matched_topics)} ===")
    if obbba_rank >= 7:
        print(f"  *** BUG FOUND: rank {obbba_rank+1} >= 8, EXCLUDED by matched_topics[:7] ***")
    else:
        print(f"  Within top 7 — should be processed")
else:
    print(f"=== obbba_vehicle_interest NOT FOUND in matched_topics! ===")

# Also check if "17" gets bumped past position 6
if "17" in augment_pubs:
    pos = augment_pubs.index("17")
    print(f"  '17' is at position {pos} in augment_pubs (0-indexed)")
    if pos >= 6:
        print(f"  *** BUG FOUND: position {pos} >= 6, EXCLUDED by augment_pubs[:6] ***")
else:
    print(f"  '17' NOT in augment_pubs at all!")
