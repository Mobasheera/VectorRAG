import torch
import numpy as np

from sentence_transformers import CrossEncoder

# Use absolute imports instead of relative
from config import (
    NLI_MODEL,
    MIN_TRUST_SCORE,
    NLI_MIN_SEMANTIC_SCORE,
    NLI_MAX_EVIDENCE
)


# ============================================================
# DEVICE
# ============================================================

def get_device():
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


DEVICE = get_device()


# ============================================================
# CONFIGURATION
# ============================================================

print("=" * 60)
print("NLI VERIFIER")
print("=" * 60)

print("Model:", NLI_MODEL)
print("Device:", DEVICE)
print("Minimum semantic score:", NLI_MIN_SEMANTIC_SCORE)
print("Minimum trust score:", MIN_TRUST_SCORE)
print("Maximum NLI evidence:", NLI_MAX_EVIDENCE)
print("=" * 60)


# ============================================================
# LOAD NLI MODEL
# ============================================================

print("Loading NLI model...")

model = CrossEncoder(
    NLI_MODEL,
    device=DEVICE
)

print("NLI model loaded.")
print("=" * 60)


# ============================================================
# LABEL MAPPING
# ============================================================

LABEL_MAPPING = {
    0: "contradiction",
    1: "entailment",
    2: "neutral"
}


# ============================================================
# SAFE FLOAT
# ============================================================

def safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


# ============================================================
# NORMALIZE TEXT
# ============================================================

def normalize_text(text):
    if not text:
        return ""
    return " ".join(str(text).lower().split())


# ============================================================
# SEMANTIC SCORE
# ============================================================

def get_semantic_score(evidence):
    # Prefer combined_score because this is the score already
    # calculated by the RAG pipeline.
    if "combined_score" in evidence:
        return safe_float(evidence.get("combined_score"))

    # Compatibility with older versions
    if "evidence_score" in evidence:
        return safe_float(evidence.get("evidence_score"))

    if "semantic_score" in evidence:
        return safe_float(evidence.get("semantic_score"))

    if "similarity" in evidence:
        return safe_float(evidence.get("similarity"))

    return 0.0


# ============================================================
# TRUST SCORE
# ============================================================

def get_evidence_trust(evidence):
    return safe_float(
        evidence.get(
            "trust_score",
            evidence.get(
                "trust_weight",
                0.0
            )
        )
    )


# ============================================================
# TRUST LEVEL
# ============================================================

def get_trust_level(trust_score):
    if trust_score >= 0.90:
        return "very_high"
    if trust_score >= 0.70:
        return "high"
    if trust_score >= 0.50:
        return "medium"
    return "low"


# ============================================================
# LEXICAL OVERLAP
# ============================================================

def lexical_overlap(claim, evidence):
    claim_words = set(normalize_text(claim).split())
    evidence_words = set(normalize_text(evidence).split())

    if not claim_words:
        return 0.0

    common = claim_words & evidence_words
    return len(common) / len(claim_words)


# ============================================================
# IMPORTANT PHRASE MATCH
# ============================================================

def phrase_match_score(claim, evidence):
    claim_text = normalize_text(claim)
    evidence_text = normalize_text(evidence)

    # Exact sentence
    if claim_text and claim_text in evidence_text:
        return 1.0

    # Important domain phrases
    important_phrases = [
        "revolves around the sun",
        "revolve around the sun",
        "orbits the sun",
        "orbit around the sun",
        "complete one orbit",
        "one complete orbit",
        "365 days",
        "365.256 days",
        "30 days"
    ]

    matched = 0
    for phrase in important_phrases:
        if phrase in claim_text and phrase in evidence_text:
            matched += 1

    if matched >= 2:
        return 1.0
    if matched == 1:
        return 0.75

    return 0.0


# ============================================================
# EVIDENCE WEIGHT
# ============================================================

def calculate_evidence_weight(claim, evidence):
    semantic = get_semantic_score(evidence)
    trust = get_evidence_trust(evidence)
    lexical = lexical_overlap(claim, evidence.get("text", ""))
    phrase = phrase_match_score(claim, evidence.get("text", ""))

    # Existing evidence weighting philosophy
    weight = (
        semantic * 0.50
        +
        trust * 0.25
        +
        lexical * 0.15
        +
        phrase * 0.10
    )

    return max(0.0, min(weight, 1.0))


# ============================================================
# SOFTMAX
# ============================================================

def softmax(values):
    values = np.asarray(values, dtype=np.float32)
    values = values - np.max(values)
    exponentials = np.exp(values)
    total = np.sum(exponentials)

    if total == 0:
        return np.array([0.0, 0.0, 1.0], dtype=np.float32)

    return exponentials / total


# ============================================================
# CONVERT NLI OUTPUT
# ============================================================

def convert_nli_output(prediction):
    prediction = np.asarray(prediction, dtype=np.float32)
    prediction = np.squeeze(prediction)

    # Three-class NLI model
    if prediction.ndim == 1 and len(prediction) == 3:
        total = float(np.sum(prediction))

        # Some CrossEncoder versions return probabilities
        # when apply_softmax=True.
        # Other versions return logits.
        # Detect which one we received.
        if (
            np.all(prediction >= 0)
            and
            np.all(prediction <= 1)
            and
            abs(total - 1.0) < 0.01
        ):
            probabilities = prediction
        else:
            probabilities = softmax(prediction)

        contradiction = float(probabilities[0])
        entailment = float(probabilities[1])
        neutral = float(probabilities[2])

        # Final normalization safeguard
        probability_total = contradiction + entailment + neutral

        if probability_total <= 0:
            contradiction = 0.0
            entailment = 0.0
            neutral = 1.0
        else:
            contradiction /= probability_total
            entailment /= probability_total
            neutral /= probability_total

        return {
            "contradiction": contradiction,
            "entailment": entailment,
            "neutral": neutral
        }

    # Unexpected output
    return {
        "contradiction": 0.0,
        "entailment": 0.0,
        "neutral": 1.0
    }


# ============================================================
# REMOVE DUPLICATE EVIDENCE
# ============================================================

def remove_duplicate_evidence(evidence_items):
    unique = []
    seen = set()

    for item in evidence_items:
        text = normalize_text(item.get("text", ""))
        url = normalize_text(item.get("url", ""))

        # Prefer URL + text.
        # This prevents the same chunk being processed twice.
        key = (url, text)

        if key in seen:
            continue

        seen.add(key)
        unique.append(item)

    return unique


# ============================================================
# FILTER EVIDENCE
# ============================================================

def filter_evidence(claim, evidence_items):
    relevant = []
    ignored = []

    for evidence in evidence_items:
        semantic_score = get_semantic_score(evidence)
        trust_score = get_evidence_trust(evidence)

        # SEMANTIC FILTER
        if semantic_score < NLI_MIN_SEMANTIC_SCORE:
            print("Evidence rejected:", "semantic score too low", semantic_score)
            ignored.append({
                **evidence,
                "ignore_reason": "semantic_score_too_low"
            })
            continue

        # TRUST FILTER
        if trust_score < MIN_TRUST_SCORE:
            print("Evidence rejected:", "trust score too low", trust_score)
            ignored.append({
                **evidence,
                "ignore_reason": "trust_score_too_low"
            })
            continue

        # COPY EVIDENCE
        item = dict(evidence)

        # Calculate useful scores
        lexical_score = lexical_overlap(claim, item.get("text", ""))
        phrase_bonus = phrase_match_score(claim, item.get("text", ""))
        evidence_weight = calculate_evidence_weight(claim, item)

        item["semantic_score"] = semantic_score
        item["trust_score"] = trust_score
        item["trust_level"] = item.get(
            "trust_level",
            get_trust_level(trust_score)
        )
        item["lexical_score"] = lexical_score
        item["phrase_bonus"] = phrase_bonus
        item["evidence_weight"] = evidence_weight

        relevant.append(item)

    # Sort strongest evidence first
    relevant.sort(
        key=lambda x: (
            x.get("evidence_weight", 0.0),
            x.get("semantic_score", 0.0)
        ),
        reverse=True
    )

    # Maximum NLI evidence
    relevant = relevant[:NLI_MAX_EVIDENCE]

    return relevant, ignored


# ============================================================
# VERIFY CLAIM
# ============================================================

def verify_claim_against_evidence(claim, evidence_items):
    # ========================================================
    # EMPTY CLAIM
    # ========================================================

    if not claim:
        return {
            "contradiction": 0.0,
            "entailment": 0.0,
            "neutral": 1.0,
            "verdict": "INSUFFICIENT EVIDENCE",
            "evidence_used": 0,
            "evidence_ignored": 0,
            "evidence_details": [],
            "nli_evidence": [],
            "source_agreement": 0.0,
            "supporting_sources": 0,
            "contradicting_sources": 0
        }

    # ========================================================
    # EMPTY EVIDENCE
    # ========================================================

    if not evidence_items:
        return {
            "contradiction": 0.0,
            "entailment": 0.0,
            "neutral": 1.0,
            "verdict": "INSUFFICIENT EVIDENCE",
            "evidence_used": 0,
            "evidence_ignored": 0,
            "evidence_details": [],
            "nli_evidence": [],
            "source_agreement": 0.0,
            "supporting_sources": 0,
            "contradicting_sources": 0
        }

    # ========================================================
    # REMOVE DUPLICATES
    # ========================================================

    evidence_items = remove_duplicate_evidence(evidence_items)

    # ========================================================
    # FILTER
    # ========================================================

    relevant, ignored = filter_evidence(claim, evidence_items)

    print()
    print("NLI EVIDENCE FILTER")
    print("Input evidence:", len(evidence_items))
    print("Relevant evidence:", len(relevant))
    print("Ignored evidence:", len(ignored))

    # ========================================================
    # NO RELEVANT EVIDENCE
    # ========================================================

    if not relevant:
        print()
        print("NLI SCORES:")
        print("Contradiction:", 0.0)
        print("Entailment:", 0.0)
        print("Neutral:", 1.0)
        print()
        print("Evidence used:", 0)
        print("Evidence ignored:", len(ignored))
        print()
        print("FINAL VERDICT:")
        print("INSUFFICIENT EVIDENCE")

        return {
            "contradiction": 0.0,
            "entailment": 0.0,
            "neutral": 1.0,
            "verdict": "INSUFFICIENT EVIDENCE",
            "evidence_used": 0,
            "evidence_ignored": len(ignored),
            "evidence_details": [],
            "nli_evidence": [],
            "source_agreement": 0.0,
            "supporting_sources": 0,
            "contradicting_sources": 0
        }

    # ========================================================
    # PREPARE NLI PAIRS
    # ========================================================

    pairs = []
    for item in relevant:
        pairs.append([
            item.get("text", ""),
            claim
        ])

    # ========================================================
    # MODEL PREDICTION
    # ========================================================

    raw_predictions = model.predict(
        pairs,
        apply_softmax=False
    )

    # ========================================================
    # PROCESS RESULTS
    # ========================================================

    details = []

    for item, prediction in zip(relevant, raw_predictions):
        probabilities = convert_nli_output(prediction)

        detail = {
            "semantic_score": round(item["semantic_score"], 4),
            "trust_score": round(item["trust_score"], 4),
            "lexical_score": round(item["lexical_score"], 4),
            "phrase_bonus": round(item["phrase_bonus"], 4),
            "evidence_weight": round(item["evidence_weight"], 4),
            "contradiction": round(probabilities["contradiction"], 4),
            "entailment": round(probabilities["entailment"], 4),
            "neutral": round(probabilities["neutral"], 4),
            "text": item.get("text", ""),
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "domain": item.get("domain", ""),
            "trust_level": item.get("trust_level", ""),
            "source_type": item.get("source_type", "")
        }

        details.append(detail)

    # ========================================================
    # PRINT NLI EVIDENCE
    # ========================================================

    for index, detail in enumerate(details, start=1):
        print()
        print("NLI Evidence", index)
        print("Semantic score:", detail["semantic_score"])
        print("Trust weight:", detail["trust_score"])
        print("Lexical score:", detail["lexical_score"])
        print("Phrase bonus:", detail["phrase_bonus"])
        print("Evidence weight:", detail["evidence_weight"])
        print("Contradiction:", detail["contradiction"])
        print("Entailment:", detail["entailment"])
        print("Neutral:", detail["neutral"])

    # ========================================================
    # STRONG EVIDENCE
    # ========================================================

    strong_support = []
    strong_contradiction = []

    for detail in details:
        # Strong contradiction
        if (
            detail["contradiction"] >= 0.70
            and
            detail["evidence_weight"] >= 0.60
        ):
            strong_contradiction.append(detail)

        # Strong entailment
        if (
            detail["entailment"] >= 0.70
            and
            detail["evidence_weight"] >= 0.60
        ):
            strong_support.append(detail)

    # ========================================================
    # SOURCE AGREEMENT
    # ========================================================

    supporting_sources = set()
    contradicting_sources = set()

    for detail in details:
        source = detail.get("domain") or detail.get("url")

        if not source:
            continue

        if detail["entailment"] >= 0.70:
            supporting_sources.add(source)

        if detail["contradiction"] >= 0.70:
            contradicting_sources.add(source)

    # ========================================================
    # WEIGHTED AGGREGATION
    # ========================================================

    total_weight = sum(
        max(detail["evidence_weight"], 0.01)
        for detail in details
    )

    if total_weight <= 0:
        total_weight = 1.0

    contradiction = (
        sum(
            detail["contradiction"] * max(detail["evidence_weight"], 0.01)
            for detail in details
        )
        / total_weight
    )

    entailment = (
        sum(
            detail["entailment"] * max(detail["evidence_weight"], 0.01)
            for detail in details
        )
        / total_weight
    )

    neutral = (
        sum(
            detail["neutral"] * max(detail["evidence_weight"], 0.01)
            for detail in details
        )
        / total_weight
    )

    # ========================================================
    # NORMALIZE FINAL SCORES
    # ========================================================

    total_probability = contradiction + entailment + neutral

    if total_probability > 0:
        contradiction /= total_probability
        entailment /= total_probability
        neutral /= total_probability

    # ========================================================
    # FINAL VERDICT
    # ========================================================

    # IMPORTANT:
    # Strong direct contradiction gets priority.
    # This prevents:
    # Wikipedia contradiction = 0.8
    # NASA contradiction     = 0.8
    # from being diluted by unrelated evidence.

    if strong_contradiction:
        verdict = "CONTRADICTED"
    elif strong_support:
        verdict = "SUPPORTED"
    elif (
        contradiction >= 0.55
        and
        contradiction > entailment
    ):
        verdict = "CONTRADICTED"
    elif (
        entailment >= 0.55
        and
        entailment > contradiction
    ):
        verdict = "SUPPORTED"
    elif (
        entailment >= 0.35
        and
        contradiction >= 0.35
    ):
        verdict = "PARTIALLY SUPPORTED"
    else:
        verdict = "INSUFFICIENT EVIDENCE"

    # ========================================================
    # SOURCE AGREEMENT
    # ========================================================

    total_sources = len(supporting_sources) + len(contradicting_sources)

    if total_sources > 0:
        if len(contradicting_sources) > len(supporting_sources):
            source_agreement = len(contradicting_sources) / total_sources
        elif len(supporting_sources) > len(contradicting_sources):
            source_agreement = len(supporting_sources) / total_sources
        else:
            source_agreement = 0.5
    else:
        source_agreement = 0.0

    # ========================================================
    # ROUND SCORES
    # ========================================================

    contradiction = round(contradiction, 4)
    entailment = round(entailment, 4)
    neutral = round(neutral, 4)
    source_agreement = round(source_agreement, 4)

    # ========================================================
    # PRINT FINAL RESULT
    # ========================================================

    print()
    print("NLI SCORES:")
    print("Contradiction:", contradiction)
    print("Entailment:", entailment)
    print("Neutral:", neutral)
    print()
    print("Evidence used:", len(details))
    print("Evidence ignored:", len(ignored))
    print()
    print("FINAL VERDICT:")
    print(verdict)

    # ========================================================
    # RETURN
    # ========================================================

    return {
        "contradiction": contradiction,
        "entailment": entailment,
        "neutral": neutral,
        "verdict": verdict,
        "evidence_used": len(details),
        "evidence_ignored": len(ignored),
        "evidence_details": details,
        "nli_evidence": details,
        "source_agreement": source_agreement,
        "supporting_sources": len(supporting_sources),
        "contradicting_sources": len(contradicting_sources)
    }


# ============================================================
# CLASSIFY VERDICT
# ============================================================

def classify_verdict(entailment, contradiction, neutral):
    entailment = safe_float(entailment)
    contradiction = safe_float(contradiction)
    neutral = safe_float(neutral)

    # Strong contradiction
    if contradiction >= 0.70:
        return "CONTRADICTED"

    # Strong support
    if entailment >= 0.70:
        return "SUPPORTED"

    # Mixed evidence
    if entailment >= 0.35 and contradiction >= 0.35:
        return "PARTIALLY SUPPORTED"

    # Moderate contradiction
    if contradiction >= 0.55 and contradiction > entailment:
        return "CONTRADICTED"

    # Moderate support
    if entailment >= 0.55 and entailment > contradiction:
        return "SUPPORTED"

    # Otherwise
    return "INSUFFICIENT EVIDENCE"