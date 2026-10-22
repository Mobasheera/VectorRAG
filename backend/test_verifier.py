from backend.verifier import (
    verify_claim_against_evidence
)


# ============================================================
# TEST FUNCTION
# ============================================================

def run_test(
    test_name,
    claim,
    evidence_items
):

    print()
    print("=" * 70)

    print(test_name)

    print("=" * 70)


    print()
    print("CLAIM:")

    print(claim)


    print()
    print("EVIDENCE:")


    for item in evidence_items:

        print()

        print(
            "Score:",
            item["combined_score"]
        )

        print(
            "Text:",
            item["text"]
        )


    # --------------------------------------------------------
    # RUN VERIFICATION
    # --------------------------------------------------------

    result = verify_claim_against_evidence(

        claim,

        evidence_items

    )


    print()
    print("NLI SCORES:")


    print(

        "Contradiction:",

        result[
            "contradiction"
        ]

    )


    print(

        "Entailment:",

        result[
            "entailment"
        ]

    )


    print(

        "Neutral:",

        result[
            "neutral"
        ]

    )


    print()
    print(

        "Evidence used:",

        result[
            "evidence_used"
        ]

    )


    print(

        "Evidence ignored:",

        result.get(
            "evidence_ignored",
            0
        )

    )


    # --------------------------------------------------------
    # VERDICT
    # --------------------------------------------------------

    verdict = result["verdict"]


    print()
    print("FINAL VERDICT:")

    print(verdict)


# ============================================================
# TEST 1
# SUPPORTED
# ============================================================

run_test(

    "TEST 1 - SUPPORTED CLAIM",

    "The Earth revolves around the Sun.",

    [

        {
            "text":
                """
                Earth revolves in orbit around the Sun
                and completes one orbit in approximately
                365 days.
                """,

            "semantic_score": 0.75,

            "combined_score": 0.75,

            "trust_score": 1.0,

            "trust_level":
                "very_high",

            "title":
                "NASA",

            "url":
                "https://science.nasa.gov/"
        }
    ]

)


# ============================================================
# TEST 2
# CONTRADICTED
# ============================================================

run_test(

    "TEST 2 - CONTRADICTED CLAIM",

    "The Earth takes 30 days to revolve around the Sun.",

    [

        {

            "text":
                """
                Earth revolves around the Sun and takes
                approximately 365 days to complete one orbit.
                """,

            "semantic_score":
                0.75,

            "combined_score":
                0.75,

            "trust_score": 1.0,

            "trust_level":
                "very_high",

            "title":
                "NASA",

            "url":
                "https://science.nasa.gov/"

        }

    ]

)


# ============================================================
# TEST 3
# UNRELATED EVIDENCE
# ============================================================

run_test(

    "TEST 3 - UNRELATED EVIDENCE",

    "The Earth revolves around the Sun.",

    [

        {

            "text":
                """
                The Earth has one natural satellite called
                the Moon.
                """,

            "semantic_score":
                0.25,

            "combined_score":
                0.25,

            "trust_level":
                "very_high",

            "title":
                "NASA",

            "url":
                "https://science.nasa.gov/"

        }

    ]

)