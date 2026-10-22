import os
from dotenv import load_dotenv

# ============================================================
# LOAD ENVIRONMENT
# ============================================================
load_dotenv()

# ============================================================
# QDRANT
# ============================================================
QDRANT_URL = os.getenv(
    "QDRANT_URL",
    "http://127.0.0.1:6333"
)
QDRANT_COLLECTION = os.getenv(
    "QDRANT_COLLECTION",
    "trusted_web_sources"
)

# ============================================================
# EMBEDDING MODEL
# ============================================================
EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL",
    "sentence-transformers/all-MiniLM-L6-v2"
)

# ============================================================
# NLI MODEL
# ============================================================
NLI_MODEL = os.getenv(
    "NLI_MODEL",
    "cross-encoder/nli-MiniLM2-L6-H768"
)

# ============================================================
# WEB SEARCH
# ============================================================
MAX_WEB_RESULTS = int(
    os.getenv(
        "MAX_WEB_RESULTS",
        "8"
    )
)

# ============================================================
# QDRANT RETRIEVAL
# ============================================================
TOP_K_QDRANT = int(
    os.getenv(
        "TOP_K_QDRANT",
        "12"
    )
)

# Minimum similarity required for a retrieved
# Qdrant chunk to be considered relevant.
MIN_RETRIEVAL_SIMILARITY = float(
    os.getenv(
        "MIN_RETRIEVAL_SIMILARITY",
        "0.40"
    )
)

# Number of final evidence chunks that can
# be passed to the NLI verifier.
MAX_FINAL_EVIDENCE = int(
    os.getenv(
        "MAX_FINAL_EVIDENCE",
        "8"
    )
)

# ============================================================
# TRUST
# ============================================================
MIN_TRUST_SCORE = float(
    os.getenv(
        "MIN_TRUST_SCORE",
        "0.70"
    )
)

# ============================================================
# NLI EVIDENCE FILTERING
# ============================================================
NLI_MIN_SEMANTIC_SCORE = float(
    os.getenv(
        "NLI_MIN_SEMANTIC_SCORE",
        "0.45"
    )
)

NLI_MAX_EVIDENCE = int(
    os.getenv(
        "NLI_MAX_EVIDENCE",
        "5"
    )
)

# ============================================================
# CHUNKING
# ============================================================
CHUNK_SIZE = int(
    os.getenv(
        "CHUNK_SIZE",
        "900"
    )
)

CHUNK_OVERLAP = int(
    os.getenv(
        "CHUNK_OVERLAP",
        "150"
    )
)

# ============================================================
# IMPROVED EVIDENCE RELEVANCE
# ============================================================
MIN_LEXICAL_RELEVANCE = float(
    os.getenv(
        "MIN_LEXICAL_RELEVANCE",
        "0.20"
    )
)

# Minimum phrase overlap required for direct relevance.
MIN_PHRASE_RELEVANCE = float(
    os.getenv(
        "MIN_PHRASE_RELEVANCE",
        "0.15"
    )
)

# Final relevance score required before NLI.
MIN_FINAL_RELEVANCE = float(
    os.getenv(
        "MIN_FINAL_RELEVANCE",
        "0.50"
    )
)

# Weight used when calculating the improved
# final relevance score.
FINAL_SEMANTIC_WEIGHT = float(
    os.getenv(
        "FINAL_SEMANTIC_WEIGHT",
        "0.45"
    )
)
FINAL_LEXICAL_WEIGHT = float(
    os.getenv(
        "FINAL_LEXICAL_WEIGHT",
        "0.30"
    )
)
FINAL_PHRASE_WEIGHT = float(
    os.getenv(
        "FINAL_PHRASE_WEIGHT",
        "0.15"
    )
)
FINAL_TRUST_WEIGHT = float(
    os.getenv(
        "FINAL_TRUST_WEIGHT",
        "0.10"
    )
)