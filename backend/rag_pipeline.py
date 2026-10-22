import hashlib

from .config import (
    TOP_K_QDRANT,
    MIN_TRUST_SCORE,
    MIN_RETRIEVAL_SIMILARITY,
    MAX_FINAL_EVIDENCE
)

from .embeddings import (
    embed_text,
    embed_texts
)

from .web_search import (
    search_web
)

from .document_processor import (
    process_url
)

from .trusted_sources import (
    get_domain,
    get_trust_score,
    get_source_type
)

from .qdrant_manager import (
    qdrant_manager
)

from .verifier import (
    verify_claim_against_evidence
)


# =========================================================
# POINT ID
# =========================================================

def make_point_id(
    url,
    chunk
):

    value = (
        url
        +
        "::"
        +
        chunk
    )

    digest = hashlib.md5(
        value.encode("utf-8")
    ).hexdigest()

    return int(
        digest[:15],
        16
    )


# =========================================================
# INDEX SEARCH RESULTS
# =========================================================

def index_search_results(
    search_results
):

    documents = []

    for result in search_results:

        url = result["url"]

        chunks = process_url(
            url
        )

        if not chunks:
            continue

        vectors = embed_texts(
            chunks
        )

        for chunk, vector in zip(
            chunks,
            vectors
        ):

            documents.append({

                "id":
                    make_point_id(
                        url,
                        chunk
                    ),

                "vector":
                    vector,

                "text":
                    chunk,

                "url":
                    url,

                "title":
                    result.get(
                        "title",
                        ""
                    ),

                "domain":
                    get_domain(
                        url
                    ),

                "trust_score":
                    get_trust_score(
                        url
                    ),

                "source_type":
                    get_source_type(
                        url
                    )

            })

    if documents:

        qdrant_manager.upsert_documents(
            documents
        )

    return len(
        documents
    )


# =========================================================
# RETRIEVE FROM QDRANT
# =========================================================

def retrieve_from_qdrant(
    claim
):

    query_vector = embed_text(
        claim
    )

    results = qdrant_manager.search(

        query_vector,

        limit=TOP_K_QDRANT

    )

    evidence = []

    for result in results:

        payload = (
            result.payload
            or {}
        )

        similarity = float(
            result.score
        )

        # -------------------------------------------------
        # Minimum retrieval similarity
        # -------------------------------------------------

        if similarity < MIN_RETRIEVAL_SIMILARITY:

            continue

        evidence.append({

            "text":
                payload.get(
                    "text",
                    ""
                ),

            "url":
                payload.get(
                    "url",
                    ""
                ),

            "title":
                payload.get(
                    "title",
                    ""
                ),

            "domain":
                payload.get(
                    "domain",
                    ""
                ),

            "trust_score":
                float(
                    payload.get(
                        "trust_score",
                        0.0
                    )
                ),

            "source_type":
                payload.get(
                    "source_type",
                    ""
                ),

            "similarity":
                similarity

        })

    return evidence


# =========================================================
# RANK EVIDENCE
# =========================================================

def rank_evidence(
    evidence
):

    for item in evidence:

        similarity = float(
            item.get(
                "similarity",
                0.0
            )
        )

        trust = float(
            item.get(
                "trust_score",
                0.0
            )
        )

        item[
            "evidence_score"
        ] = round(

            (
                similarity
                * 0.70
            )

            +

            (
                trust
                * 0.30
            ),

            4

        )

    evidence.sort(

        key=lambda x:
            x.get(
                "evidence_score",
                0.0
            ),

        reverse=True

    )

    return evidence


# =========================================================
# REMOVE DUPLICATE SOURCES
# =========================================================

def remove_duplicate_sources(
    evidence
):

    unique = []

    seen = set()

    for item in evidence:

        url = item.get(
            "url",
            ""
        )

        if url in seen:

            continue

        seen.add(
            url
        )

        unique.append(
            item
        )

    return unique


# =========================================================
# SOURCE AGREEMENT
# =========================================================

def calculate_source_agreement(
    evidence
):

    if not evidence:

        return 0.0

    source_scores = []

    seen_domains = set()

    for item in evidence:

        domain = item.get(
            "domain",
            ""
        )

        if not domain:

            domain = item.get(
                "url",
                ""
            )

        if domain in seen_domains:

            continue

        seen_domains.add(
            domain
        )

        source_scores.append(
            float(
                item.get(
                    "evidence_score",
                    0.0
                )
            )
        )

    if not source_scores:

        return 0.0

    average = (
        sum(source_scores)
        /
        len(source_scores)
    )

    return round(
        average,
        4
    )


# =========================================================
# TRUST LEVEL
# =========================================================

def get_trust_level(
    trust_score
):

    trust_score = float(
        trust_score
    )

    if trust_score >= 0.90:

        return "very_high"

    if trust_score >= 0.75:

        return "high"

    if trust_score >= 0.50:

        return "medium"

    return "low"


# =========================================================
# ENRICH EVIDENCE
# =========================================================

def enrich_evidence(
    evidence
):

    for item in evidence:

        trust_score = float(
            item.get(
                "trust_score",
                0.0
            )
        )

        item[
            "trust_level"
        ] = get_trust_level(
            trust_score
        )

    return evidence


# =========================================================
# BUILD SOURCE GROUPS
# =========================================================

def build_source_groups(
    evidence
):

    groups = {}

    for item in evidence:

        url = item.get(
            "url",
            ""
        )

        if not url:

            continue

        if url not in groups:

            trust_score = float(
                item.get(
                    "trust_score",
                    0.0
                )
            )

            groups[url] = {

                "title":
                    item.get(
                        "title",
                        ""
                    ),

                "url":
                    url,

                "trust_level":
                    item.get(
                        "trust_level",
                        get_trust_level(
                            trust_score
                        )
                    ),

                "trust_weight":
                    trust_score,

                "best_score":
                    float(
                        item.get(
                            "evidence_score",
                            0.0
                        )
                    ),

                "chunks": []

            }

        else:

            current_score = float(
                item.get(
                    "evidence_score",
                    0.0
                )
            )

            if (
                current_score
                >
                groups[url]["best_score"]
            ):

                groups[url][
                    "best_score"
                ] = current_score

        groups[url]["chunks"].append({

            "text":
                item.get(
                    "text",
                    ""
                ),

            "semantic_score":
                round(
                    float(
                        item.get(
                            "semantic_score",
                            item.get(
                                "similarity",
                                0.0
                            )
                        )
                    ),
                    4
                ),

            "combined_score":
                round(
                    float(
                        item.get(
                            "combined_score",
                            item.get(
                                "evidence_score",
                                0.0
                            )
                        )
                    ),
                    4
                )

        })

    return list(
        groups.values()
    )


# =========================================================
# BUILD SOURCE OUTPUT
# =========================================================

def build_sources_output(
    search_results
):

    sources = []

    for result in search_results:

        trust_score = float(
            result.get(
                "trust_score",
                0.0
            )
        )

        sources.append({

            "title":
                result.get(
                    "title",
                    ""
                ),

            "url":
                result.get(
                    "url",
                    ""
                ),

            "snippet":
                result.get(
                    "snippet",
                    ""
                ),

            "domain":
                result.get(
                    "domain",
                    ""
                ),

            "source_type":
                result.get(
                    "source_type",
                    ""
                ),

            "trust_level":
                get_trust_level(
                    trust_score
                ),

            "trust_weight":
                trust_score

        })

    return sources


# =========================================================
# RUN RAG
# =========================================================

def run_rag(
    claim
):

    print()
    print("=" * 70)
    print("RAG PIPELINE")
    print("=" * 70)
    print("Claim:", claim)
    print("=" * 70)

    # =====================================================
    # STEP 1 - LIVE WEB SEARCH
    # =====================================================

    search_results = search_web(
        claim
    )

    print(
        "Web search results:",
        len(search_results)
    )

    # =====================================================
    # STEP 2 - INDEX TRUSTED SOURCES
    # =====================================================

    indexed_chunks = (
        index_search_results(
            search_results
        )
    )

    print(
        "Newly indexed chunks:",
        indexed_chunks
    )

    # =====================================================
    # STEP 3 - RETRIEVE FROM QDRANT
    # =====================================================

    retrieved_evidence = (
        retrieve_from_qdrant(
            claim
        )
    )

    print(
        "Qdrant retrieved:",
        len(retrieved_evidence)
    )

    # =====================================================
    # STEP 4 - TRUST FILTER
    # =====================================================

    trusted_evidence = [

        item

        for item
        in retrieved_evidence

        if float(
            item.get(
                "trust_score",
                0.0
            )
        )
        >= MIN_TRUST_SCORE

    ]

    # =====================================================
    # STEP 5 - RANK
    # =====================================================

    trusted_evidence = rank_evidence(
        trusted_evidence
    )

    # =====================================================
    # STEP 6 - CLAIM RELEVANCE
    #
    # Keep evidence above retrieval threshold.
    # The verifier performs the finer sentence-level
    # relevance filtering.
    # =====================================================

    relevant_evidence = []

    ignored_count = 0

    for item in trusted_evidence:

        similarity = float(
            item.get(
                "similarity",
                0.0
            )
        )

        if similarity >= MIN_RETRIEVAL_SIMILARITY:

            relevant_evidence.append(
                item
            )

        else:

            ignored_count += 1

    print(
        "Claim-relevant evidence:",
        len(relevant_evidence)
    )

    print(
        "Ignored evidence:",
        ignored_count
    )

    # =====================================================
    # STEP 7 - ENRICH EVIDENCE
    # =====================================================

    relevant_evidence = enrich_evidence(
        relevant_evidence
    )

    # =====================================================
    # STEP 8 - KEEP BEST EVIDENCE
    #
    # Keep more than one source whenever possible.
    # This preserves cross-source verification.
    # =====================================================

    top_evidence = (
        relevant_evidence[
            :MAX_FINAL_EVIDENCE
        ]
    )

    # =====================================================
    # STEP 9 - NLI VERIFICATION
    #
    # verifier.py performs:
    #
    #   semantic filtering
    #   sentence extraction
    #   lexical analysis
    #   phrase matching
    #   NLI
    #   source agreement
    #
    # =====================================================

    nli_result = (
        verify_claim_against_evidence(

            claim,

            top_evidence

        )
    )

    # =====================================================
    # STEP 10 - FINAL VERDICT
    # =====================================================

    verdict = nli_result.get(
        "verdict",
        "INSUFFICIENT EVIDENCE"
    )

    # =====================================================
    # STEP 11 - CONFIDENCE
    # =====================================================

    entailment = float(
        nli_result.get(
            "entailment",
            0.0
        )
    )

    contradiction = float(
        nli_result.get(
            "contradiction",
            0.0
        )
    )

    neutral = float(
        nli_result.get(
            "neutral",
            1.0
        )
    )

    if verdict == "SUPPORTED":

        confidence = entailment

    elif verdict == "CONTRADICTED":

        confidence = contradiction

    elif verdict == "PARTIALLY SUPPORTED":

        confidence = max(
            entailment,
            contradiction
        )

    else:

        confidence = (
            1.0 - neutral
        )

    confidence = max(
        0.0,
        min(
            confidence,
            1.0
        )
    )

    # =====================================================
    # STEP 12 - SOURCE GROUPS
    # =====================================================

    source_groups = build_source_groups(
        top_evidence
    )

    # =====================================================
    # STEP 13 - SOURCE AGREEMENT
    # =====================================================

    source_agreement = (
        nli_result.get(
            "source_agreement",
            calculate_source_agreement(
                top_evidence
            )
        )
    )

    # =====================================================
    # STEP 14 - FINAL SOURCES
    # =====================================================

    sources = build_sources_output(
        search_results
    )

    # =====================================================
    # RETURN RESULT
    # =====================================================

    return {

        "claim":
            claim,

        "verdict":
            verdict,

        "confidence":
            round(
                confidence * 100,
                2
            ),

        "nli":
            nli_result,

        "web_sources_found":
            len(
                search_results
            ),

        "indexed_chunks":
            indexed_chunks,

        "evidence_count":
            len(
                top_evidence
            ),

        "source_count":
            len(
                source_groups
            ),

        "source_agreement":
            round(
                float(
                    source_agreement
                ),
                4
            ),

        "evidence":
            top_evidence,

        "nli_evidence":
            nli_result.get(
                "nli_evidence",
                []
            ),

        "source_groups":
            source_groups,

        "sources":
            sources

    }