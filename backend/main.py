from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from typing import List

import requests

from bs4 import BeautifulSoup

from urllib.parse import quote, urlparse

from sentence_transformers import SentenceTransformer

from qdrant_client import QdrantClient

from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
    PayloadSchemaType
)

from verifier import (
    verify_claim_against_evidence
)

from config import (
    QDRANT_URL,
    QDRANT_COLLECTION,
    EMBEDDING_MODEL,
    TOP_K_QDRANT,
    MAX_WEB_RESULTS,
    MIN_TRUST_SCORE,
    CHUNK_SIZE,
    CHUNK_OVERLAP
)

import re
import uuid

from datetime import datetime


# ============================================================
# APPLICATION
# ============================================================

app = FastAPI(

    title=
        "Adaptive RAG AI Hallucination Detector",

    version=
        "6.0"
)


# ============================================================
# CORS
# ============================================================

app.add_middleware(

    CORSMiddleware,

    allow_origins=["*"],

    allow_credentials=True,

    allow_methods=["*"],

    allow_headers=["*"]
)


# ============================================================
# CONFIGURATION
# ============================================================

QDRANT_COLLECTION_NAME = (
    QDRANT_COLLECTION
)

EMBEDDING_MODEL_NAME = (
    EMBEDDING_MODEL
)

TOP_K = TOP_K_QDRANT

WEB_RESULTS = MAX_WEB_RESULTS


# ============================================================
# CHUNKING CONFIGURATION
# ============================================================

MIN_CHUNK_WORDS = 40

MAX_CHUNK_WORDS = 150

MAX_COMBINED_WORDS = 150

# ============================================================
# TRUST LEVELS
# ============================================================

TRUST_LEVELS = {

    "very_high": 1.00,

    "high": 0.95,

    "medium": 0.85,

    "reference": 0.75

}


# ============================================================
# VERY HIGH TRUST DOMAINS
# ============================================================

VERY_HIGH_TRUST_DOMAINS = [
    "nasa.gov",
    "science.nasa.gov",
    "solarsystem.nasa.gov",
    "jpl.nasa.gov",
    "who.int",
    "un.org",
    "worldbank.org",
    "imf.org",
    "gov.in",
    "nic.in",
    "gov.uk",
    "gov",
    "pubmed.ncbi.nlm.nih.gov",
    "ncbi.nlm.nih.gov",
    "esa.int",  # European Space Agency
    "noaa.gov", # NOAA
    "usgs.gov", # US Geological Survey
]


# ============================================================
# HIGH TRUST DOMAINS
# ============================================================

HIGH_TRUST_DOMAINS = [

    "nature.com",

    "science.org",

    "sciencedirect.com",

    "ieee.org",

    "acm.org"

]


# ============================================================
# MEDIUM TRUST DOMAINS
# ============================================================

MEDIUM_TRUST_DOMAINS = [

    "edu",

    "ac.in",

    "edu.in"

]


# ============================================================
# REFERENCE DOMAINS
# ============================================================

REFERENCE_DOMAINS = [

    "wikipedia.org",

    "britannica.com"

]


# ============================================================
# REQUEST MODEL
# ============================================================

class AnalyzeRequest(BaseModel):

    answer: str

    platform: str = "Unknown"

    website: str = ""

    url: str = ""

# ============================================================
# SOURCE CLASS
# ============================================================

class Source:

    def __init__(

        self,

        title,

        url,

        snippet,

        source_type="web"

    ):

        self.title = title

        self.url = url

        self.snippet = snippet

        self.source_type = source_type


# ============================================================
# LOAD EMBEDDING MODEL
# ============================================================

print("=" * 60)

print("LOADING EMBEDDING MODEL")

print("=" * 60)

print(
    "Model:",
    EMBEDDING_MODEL_NAME
)

embedding_model = SentenceTransformer(

    EMBEDDING_MODEL_NAME

)

print(
    "Embedding model loaded."
)

print("=" * 60)


# ============================================================
# CONNECT TO QDRANT
# ============================================================

print("Connecting to Qdrant...")

def get_qdrant_client():
    """Attempt to connect to Qdrant with fallback options."""
    
    # First try: Use the URL from .env
    try:
        client = QdrantClient(url=QDRANT_URL)
        # Test connection
        client.get_collections()
        print(f"Connected to Qdrant at {QDRANT_URL}")
        return client
    except Exception as e:
        print(f"Connection to {QDRANT_URL} failed: {e}")
    
    # Second try: Use localhost
    try:
        client = QdrantClient(host="127.0.0.1", port=6333)
        client.get_collections()
        print("Connected to Qdrant at 127.0.0.1:6333")
        return client
    except Exception as e:
        print(f"Connection to 127.0.0.1:6333 failed: {e}")
    
    # Third try: Use localhost with default port
    try:
        client = QdrantClient(host="localhost", port=6333)
        client.get_collections()
        print("Connected to Qdrant at localhost:6333")
        return client
    except Exception as e:
        print(f"All connection attempts failed: {e}")
        raise RuntimeError(
            "Could not connect to Qdrant. "
            "Please make sure Qdrant is running with: docker-compose up -d"
        )

qdrant = get_qdrant_client()

# ============================================================
# INITIALIZE QDRANT
# ============================================================

def initialize_qdrant():
    vector_size = embedding_model.get_sentence_embedding_dimension()  # Fixed method name
    collections = qdrant.get_collections()
    collection_names = [collection.name for collection in collections.collections]

    if QDRANT_COLLECTION_NAME not in collection_names:
        qdrant.create_collection(
            collection_name=QDRANT_COLLECTION_NAME,
            vectors_config=VectorParams(
                size=vector_size,
                distance=Distance.COSINE
            )
        )
        print("Created Qdrant collection:", QDRANT_COLLECTION_NAME)
    else:
        print("Collection already exists:", QDRANT_COLLECTION_NAME)

    try:
        qdrant.create_payload_index(
            collection_name=QDRANT_COLLECTION_NAME,
            field_name="url",
            field_schema=PayloadSchemaType.KEYWORD
        )
        print("URL payload index ready.")
    except Exception:
        print("URL payload index already exists.")

# ============================================================
# INITIALIZE
# ============================================================

initialize_qdrant()


# ============================================================
# CLEAN TEXT
# ============================================================

def clean_text(text):
    """Removes emojis and extra whitespace, keeps it safe for processing."""
    if not text:
        return ""
    # Remove all non-ASCII (emojis, special symbols)
    text = re.sub(r'[^\x00-\x7F]+', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

# ============================================================
# NORMALIZE URL
# ============================================================

def normalize_url(url):

    if not url:

        return ""

    url = str(url).strip()

    url = url.rstrip("/")

    return url


# ============================================================
# GET DOMAIN
# ============================================================

def get_domain(url):

    try:

        hostname = urlparse(
            url
        ).hostname

        if not hostname:

            return ""

        return hostname.lower()

    except Exception:

        return ""


# ============================================================
# SOURCE TRUST
# ============================================================

def get_source_trust(url):

    domain = get_domain(url)


    # --------------------------------------------------------
    # VERY HIGH TRUST
    # --------------------------------------------------------

    for trusted_domain in (

        VERY_HIGH_TRUST_DOMAINS

    ):

        if (

            domain == trusted_domain

            or

            domain.endswith(
                "." + trusted_domain
            )

        ):

            return (

                "very_high",

                TRUST_LEVELS[
                    "very_high"
                ]

            )


    # --------------------------------------------------------
    # HIGH TRUST
    # --------------------------------------------------------

    for trusted_domain in (

        HIGH_TRUST_DOMAINS

    ):

        if (

            domain == trusted_domain

            or

            domain.endswith(
                "." + trusted_domain
            )

        ):

            return (

                "high",

                TRUST_LEVELS[
                    "high"
                ]

            )


    # --------------------------------------------------------
    # MEDIUM TRUST
    # --------------------------------------------------------

    for trusted_domain in (

        MEDIUM_TRUST_DOMAINS

    ):

        if (

            domain == trusted_domain

            or

            domain.endswith(
                "." + trusted_domain
            )

        ):

            return (

                "medium",

                TRUST_LEVELS[
                    "medium"
                ]

            )


    # --------------------------------------------------------
    # REFERENCE
    # --------------------------------------------------------

    for trusted_domain in (

        REFERENCE_DOMAINS

    ):

        if (

            domain == trusted_domain

            or

            domain.endswith(
                "." + trusted_domain
            )

        ):

            return (

                "reference",

                TRUST_LEVELS[
                    "reference"
                ]

            )


    return (

        None,

        0.0

    )


# ============================================================
# TRUSTED DOMAIN CHECK
# ============================================================

def is_trusted_domain(url):

    level, weight = (

        get_source_trust(url)

    )

    return level is not None


# ============================================================
# CLAIM EXTRACTION
# ============================================================

def extract_claims(answer: str):
    print("=" * 70)
    print("EXTRACTING CLAIMS FROM RESPONSE:")
    print(f"Response length: {len(answer)} chars")
    print(f"Response preview: {answer[:200]}...")
    print("=" * 70)
    
    # STEP 1: Clean emojis and whitespace globally FIRST
    answer = clean_text(answer)
    
    # =========================================================
    # STEP 2: SPLIT BY NEWLINES FIRST (The Bullet Point Fix)
    # =========================================================
    sentences = []
    
    # Split by actual line breaks (If AI used bullets, this catches them)
    raw_lines = answer.split('\n')
    
    if len(raw_lines) > 1:
        for line in raw_lines:
            line = line.strip()
            
            # Skip empty lines or headers (like "Examples of cybercrime:")
            if not line or line.endswith(':') or len(line) < 15:
                continue
                
            # Remove bullet symbols (e.g., "-", "*", "•")
            line = re.sub(r'^[-*•●○◆◇■□▪▫]+\s*', '', line)
            
            # If it has a dash (e.g., "Phishing – tricking people..."), 
            # split it into a clean claim
            if '–' in line or '-' in line:
                parts = re.split(r'[–-]', line, maxsplit=1)
                if len(parts) == 2:
                    # Reassemble: "Phishing tricking people..."
                    cleaned_claim = f"{parts[0].strip()} {parts[1].strip()}"
                    if len(cleaned_claim) > 20:
                        sentences.append(cleaned_claim)
                        continue
                else:
                    sentences.append(line)
            else:
                # Standard line
                if len(line) > 20:
                    sentences.append(line)
        
        if sentences:
            print(f"Method 0 (newlines/bullets): Found {len(sentences)} sentences")
    
    # =========================================================
    # STEP 3: FALLBACKS (If no newlines were found)
    # =========================================================
    if not sentences:
        # METHOD 1: Split by sentences (periods, exclamation, question)
        raw_sentences = re.split(r'(?<=[.!?])\s+', answer)
        
        if len(raw_sentences) > 1:
            sentences = [s.strip() for s in raw_sentences if s.strip()]
            print(f"Method 1 (punctuation): Found {len(sentences)} sentences")
        else:
            # METHOD 2: Split by numbered lists (1., 2., etc.)
            numbered = re.split(r'\d+\.\s+', answer)
            if len(numbered) > 1:
                sentences = [s.strip() for s in numbered if s.strip()]
                print(f"Method 2 (numbered lists): Found {len(sentences)} sentences")
            else:
                # METHOD 3: Split by bullet points
                bullets = re.split(r'[•·●○◆◇■□▪▫\-]\s*', answer)
                if len(bullets) > 1:
                    sentences = [s.strip() for s in bullets if s.strip()]
                    print(f"Method 3 (bullet points): Found {len(sentences)} sentences")
                else:
                    # METHOD 4: Split by commas for longer text
                    if len(answer) > 100:
                        comma_parts = re.split(r',\s*', answer)
                        if len(comma_parts) > 1:
                            grouped = []
                            current = ""
                            for part in comma_parts:
                                if len(current) + len(part) < 100:
                                    current += part + ", "
                                else:
                                    if current:
                                        grouped.append(current.rstrip(", "))
                                    current = part + ", "
                            if current:
                                grouped.append(current.rstrip(", "))
                            sentences = grouped
                            print(f"Method 4 (commas): Found {len(sentences)} groups")
                        else:
                            sentences = [answer]
                            print("Method 5 (fallback): Using whole response")
                    else:
                        sentences = [answer]
                        print("Method 5 (fallback): Using whole response")
    
    # =========================================================
    # STEP 4: CLEAN AND VALIDATE EACH CLAIM
    # =========================================================
    claims = []
    
    for sentence in sentences:
        # Clean the sentence again (removes any remaining special chars)
        sentence = clean_text(sentence)
        
        # Skip very short sentences (less than 15 chars)
        if len(sentence) < 15:
            continue
            
        # Skip questions
        if sentence.endswith("?"):
            continue
            
        # Skip if it's just a few words
        word_count = len(sentence.split())
        if word_count < 3:
            continue
        
        # Skip if it's a duplicate
        if sentence in claims:
            continue
            
        # Add the claim
        claims.append(sentence)
        print(f"  -> Added claim: '{sentence[:50]}...'")
    
    # =========================================================
    # STEP 5: FINAL FALLBACK
    # =========================================================
    if not claims and len(answer) > 20:
        claims.append(answer)
        print("Using whole response as fallback")
    
    print(f"\nTotal claims extracted: {len(claims)}")
    for i, claim in enumerate(claims):
        print(f"  Claim {i+1}: {claim[:80]}...")
    print("=" * 70)
    
    return claims[:15]  # Max 15 claims


# ============================================================
# CLAIM COMPLEXITY
# ============================================================

def determine_complexity(claim):

    words = claim.split()

    score = 0


    if len(words) > 25:

        score += 2


    complex_terms = [

        "why",

        "impact",

        "effect",

        "compare",

        "comparison",

        "relationship",

        "historical",

        "economic",

        "scientific",

        "research",

        "study",

        "cause",

        "result",

        "evidence",

        "according",

        "percentage",

        "statistics"

    ]


    lower_claim = claim.lower()


    for term in complex_terms:

        if term in lower_claim:

            score += 1


    if score >= 3:

        return "complex"


    return "simple"


# ============================================================
# WEB SEARCH
# ============================================================

def search_web(query):

    sources = []


    try:

        search_url = (
            "https://html.duckduckgo.com/html/"
        )


        response = requests.post(

            search_url,

            data={
                "q": query
            },

            headers={

                "User-Agent":
                    "Mozilla/5.0"

            },

            timeout=15

        )


        soup = BeautifulSoup(

            response.text,

            "html.parser"

        )


        results = soup.select(
            ".result"
        )


        for result in results[

            :WEB_RESULTS

        ]:

            link = result.select_one(

                ".result__a"

            )


            if not link:

                continue


            title = link.get_text(

                " ",

                strip=True

            )


            href = link.get(
                "href"
            )


            snippet_element = (

                result.select_one(

                    ".result__snippet"

                )

            )


            snippet = ""


            if snippet_element:

                snippet = (

                    snippet_element
                    .get_text(
                        " ",
                        strip=True
                    )

                )


            if href:

                sources.append(

                    Source(

                        title=title,

                        url=
                            normalize_url(
                                href
                            ),

                        snippet=snippet,

                        source_type=
                            "web_search"

                    )

                )


    except Exception as e:

        print(

            "Web search error:",

            e

        )


    return sources


# ============================================================
# WIKIPEDIA SEARCH
# ============================================================

def search_wikipedia(query):

    sources = []


    url = (

        "https://en.wikipedia.org/w/api.php"

    )


    params = {

        "action":
            "query",

        "list":
            "search",

        "srsearch":
            query,

        "format":
            "json",

        "utf8":
            1,

        "srlimit":
            5

    }


    try:

        response = requests.get(

            url,

            params=params,

            timeout=10,

            headers={

                "User-Agent":
                    "AdaptiveRAG-HallucinationDetector/6.0"

            }

        )


        data = response.json()


        results = (

            data

            .get(
                "query",
                {}
            )

            .get(
                "search",
                []
            )

        )


        for item in results:

            title = item[
                "title"
            ]


            page_url = (

                "https://en.wikipedia.org/wiki/"

                +

                quote(

                    title.replace(
                        " ",
                        "_"
                    )

                )

            )


            snippet = BeautifulSoup(

                item.get(
                    "snippet",
                    ""
                ),

                "html.parser"

            ).get_text(
                " "
            )


            sources.append(

                Source(

                    title=
                        "Wikipedia - "
                        + title,

                    url=
                        normalize_url(
                            page_url
                        ),

                    snippet=
                        snippet,

                    source_type=
                        "wikipedia"

                )

            )


    except Exception as e:

        print(

            "Wikipedia error:",

            e

        )


    return sources


# ============================================================
# DEDUPLICATE SOURCES
# ============================================================

def deduplicate_sources(sources):

    unique = {}


    for source in sources:

        url = normalize_url(
            source.url
        )


        if not url:

            continue


        if url not in unique:

            unique[url] = source


    return list(
        unique.values()
    )


# ============================================================
# RANK SOURCES
# ============================================================

def rank_sources(sources):

    ranked = []


    for source in sources:

        trust_level, trust_weight = (

            get_source_trust(
                source.url
            )

        )


        if trust_level is None:

            continue


        ranked.append({

            "source":
                source,

            "trust_level":
                trust_level,

            "trust_weight":
                trust_weight

        })


    ranked.sort(

        key=lambda item:
            item[
                "trust_weight"
            ],

        reverse=True

    )


    return [

        item["source"]

        for item
        in ranked

    ]


# ============================================================
# RETRIEVE SOURCES
# ============================================================

def retrieve_sources(
    claim,
    complexity
):

    # --------------------------------------------------------
    # WEB SEARCH
    # --------------------------------------------------------

    web_sources = search_web(
        claim
    )


    # --------------------------------------------------------
    # ONLY TRUSTED WEB SOURCES
    # --------------------------------------------------------

    trusted_web_sources = [

        source

        for source
        in web_sources

        if is_trusted_domain(
            source.url
        )

    ]


    # --------------------------------------------------------
    # WIKIPEDIA
    # --------------------------------------------------------

    wikipedia_sources = (

        search_wikipedia(
            claim
        )

    )


    # --------------------------------------------------------
    # COMBINE
    # --------------------------------------------------------

    all_sources = (

        trusted_web_sources

        +

        wikipedia_sources

    )


    # --------------------------------------------------------
    # REMOVE DUPLICATES
    # --------------------------------------------------------

    all_sources = (

        deduplicate_sources(
            all_sources
        )

    )


    # --------------------------------------------------------
    # RANK
    # --------------------------------------------------------

    ranked_sources = (

        rank_sources(
            all_sources
        )

    )


    return ranked_sources[:10]


# ============================================================
# FETCH WEB PAGE
# ============================================================

def fetch_webpage(url):

    try:

        response = requests.get(

            url,

            timeout=15,

            headers={

                "User-Agent":
                    "Mozilla/5.0"

            }

        )


        if response.status_code != 200:

            return ""


        soup = BeautifulSoup(

            response.text,

            "html.parser"

        )


        # ----------------------------------------------------
        # REMOVE UNNECESSARY HTML
        # ----------------------------------------------------

        for tag in soup([

            "script",

            "style",

            "nav",

            "footer",

            "header",

            "aside",

            "form",

            "noscript",

            "svg"

        ]):

            tag.decompose()


        # ----------------------------------------------------
        # EXTRACT PARAGRAPHS
        # ----------------------------------------------------

        paragraphs = []


        for paragraph in soup.find_all(
            "p"
        ):

            text = clean_text(

                paragraph.get_text(

                    " ",

                    strip=True

                )

            )


            if text:

                paragraphs.append(
                    text
                )


        # ----------------------------------------------------
        # FALLBACK
        # ----------------------------------------------------

        if not paragraphs:

            text = soup.get_text(

                " ",

                strip=True

            )


            return clean_text(
                text
            )


        return "\n".join(
            paragraphs
        )


    except Exception as e:

        print(

            "Page fetch error:",

            e

        )

        return ""


# ============================================================
# CREATE CHUNKS
# ============================================================

def create_chunks(text):

    if not text:

        return []


    # --------------------------------------------------------
    # SPLIT INTO PARAGRAPHS
    # --------------------------------------------------------

    paragraphs = [

        clean_text(
            paragraph
        )

        for paragraph
        in text.split("\n")

        if clean_text(
            paragraph
        )

    ]


    chunks = []

    current_chunk = []

    current_words = 0


    # --------------------------------------------------------
    # BUILD CHUNKS
    # --------------------------------------------------------

    for paragraph in paragraphs:

        words = paragraph.split()

        word_count = len(words)


        # ----------------------------------------------------
        # LARGE PARAGRAPH
        # ----------------------------------------------------

        if word_count > MAX_CHUNK_WORDS:

            if current_chunk:

                chunks.append(

                    " ".join(
                        current_chunk
                    )

                )

                current_chunk = []

                current_words = 0


            start = 0


            while start < word_count:

                end = min(

                    start
                    + MAX_CHUNK_WORDS,

                    word_count

                )


                piece = " ".join(

                    words[start:end]

                )


                if len(
                    piece.split()
                ) >= MIN_CHUNK_WORDS:

                    chunks.append(
                        piece
                    )


                start = end


            continue


        # ----------------------------------------------------
        # ADD TO CURRENT CHUNK
        # ----------------------------------------------------

        if (

            current_words
            + word_count

            <= MAX_CHUNK_WORDS

        ):

            current_chunk.append(
                paragraph
            )

            current_words += word_count


        else:

            if current_chunk:

                chunks.append(

                    " ".join(
                        current_chunk
                    )

                )


            current_chunk = [
                paragraph
            ]

            current_words = word_count


    # --------------------------------------------------------
    # REMAINING CHUNK
    # --------------------------------------------------------

    if current_chunk:

        chunks.append(

            " ".join(
                current_chunk
            )

        )


    # --------------------------------------------------------
    # REMOVE SMALL CHUNKS
    # --------------------------------------------------------

    final_chunks = [

        chunk

        for chunk
        in chunks

        if len(
            chunk.split()
        ) >= MIN_CHUNK_WORDS

    ]


    return final_chunks


# ============================================================
# CHECK WHETHER URL ALREADY EXISTS
# ============================================================

def url_already_indexed(url):

    normalized_url = normalize_url(
        url
    )


    try:

        result = qdrant.scroll(

            collection_name=
                QDRANT_COLLECTION_NAME,

            scroll_filter=Filter(

                must=[

                    FieldCondition(

                        key="url",

                        match=MatchValue(

                            value=
                                normalized_url

                        )

                    )

                ]

            ),

            limit=1,

            with_payload=False,

            with_vectors=False

        )


        points = result[0]


        return len(points) > 0


    except Exception as e:

        print(

            "URL lookup error:",

            e

        )

        return False


# ============================================================
# STORE DOCUMENT IN QDRANT
# ============================================================

def store_document(
    source,
    text
):

    normalized_url = normalize_url(
        source.url
    )


    # --------------------------------------------------------
    # DUPLICATE CHECK
    # --------------------------------------------------------

    if url_already_indexed(
        normalized_url
    ):

        print(

            "Already indexed:",

            normalized_url

        )

        return 0


    # --------------------------------------------------------
    # CREATE CHUNKS
    # --------------------------------------------------------

    chunks = create_chunks(
        text
    )


    if not chunks:

        print(

            "No useful chunks:",

            normalized_url

        )

        return 0


    print(

        f"Creating {len(chunks)} chunks..."

    )


    # --------------------------------------------------------
    # CREATE EMBEDDINGS
    # --------------------------------------------------------

    vectors = embedding_model.encode(

        chunks,

        normalize_embeddings=True,

        show_progress_bar=False

    )


    # --------------------------------------------------------
    # TRUST
    # --------------------------------------------------------

    trust_level, trust_weight = (

        get_source_trust(
            normalized_url
        )

    )


    # --------------------------------------------------------
    # CREATE POINTS
    # --------------------------------------------------------

    points = []


    for index, chunk in enumerate(
        chunks
    ):

        point_id = str(
            uuid.uuid4()
        )


        points.append(

            PointStruct(

                id=point_id,

                vector=
                    vectors[index].tolist(),

                payload={

                    "text":
                        chunk,

                    "title":
                        source.title,

                    "url":
                        normalized_url,

                    "source_type":
                        source.source_type,

                    "domain":
                        get_domain(
                            normalized_url
                        ),

                    "trust_score":
                        trust_weight,

                    "trust_weight":
                        trust_weight,

                    "trust_level":
                        trust_level
                        or "unknown",

                    "indexed_at":
                        datetime.utcnow()
                        .isoformat()

                }

            )

        )


    # --------------------------------------------------------
    # INSERT INTO QDRANT
    # --------------------------------------------------------

    qdrant.upsert(

        collection_name=
            QDRANT_COLLECTION_NAME,

        points=points

    )


    return len(points)


# ============================================================
# INDEX SOURCES
# ============================================================

def index_sources(sources):

    indexed_chunks = 0


    for source in sources:

        normalized_url = normalize_url(
            source.url
        )


        # ----------------------------------------------------
        # SKIP ALREADY INDEXED
        # ----------------------------------------------------

        if url_already_indexed(
            normalized_url
        ):

            print(

                "Skipping indexed source:",

                normalized_url

            )

            continue


        print(

            "Fetching source:",

            normalized_url

        )


        page_text = fetch_webpage(

            normalized_url

        )


        if not page_text:

            print(

                "Could not extract:",

                normalized_url

            )

            continue


        count = store_document(

            source,

            page_text

        )


        indexed_chunks += count


        print(

            f"Indexed {count} chunks from: "
            f"{normalized_url}"

        )


    return indexed_chunks


# ============================================================
# RETRIEVE EVIDENCE FROM QDRANT
# ============================================================

def retrieve_evidence(
    claim,
    top_k=TOP_K
):

    # --------------------------------------------------------
    # CREATE CLAIM EMBEDDING
    # --------------------------------------------------------

    query_vector = embedding_model.encode(

        claim,

        normalize_embeddings=True

    ).tolist()


    # --------------------------------------------------------
    # QDRANT SEARCH
    # --------------------------------------------------------

    try:

        results = (

            qdrant
            .query_points(

                collection_name=
                    QDRANT_COLLECTION_NAME,

                query=
                    query_vector,

                limit=
                    top_k * 3,

                with_payload=True

            )

            .points

        )

    except Exception as e:

        print(

            "Qdrant search error:",

            e

        )

        return []


    evidence = []


    # --------------------------------------------------------
    # PROCESS RESULTS
    # --------------------------------------------------------

    for result in results:

        payload = (

            result.payload

            or {}

        )


        semantic_score = float(

            result.score

        )


        trust_weight = float(

            payload.get(

                "trust_weight",

                0.5

            )

        )


        trust_level = payload.get(

            "trust_level",

            "unknown"

        )


        # ----------------------------------------------------
        # COMBINED SCORE
        # ----------------------------------------------------

        combined_score = (

            semantic_score
            * trust_weight

        )


        evidence.append({

            "semantic_score":

                round(

                    semantic_score,

                    4

                ),

            "trust_weight":

                round(

                    trust_weight,

                    2

                ),

            "combined_score":

                round(

                    combined_score,

                    4

                ),

            "trust_level":

                trust_level,

            "text":

                payload.get(

                    "text",

                    ""

                ),

            "title":

                payload.get(

                    "title",

                    ""

                ),

            "url":

                payload.get(

                    "url",

                    ""

                ),

            "source_type":

                payload.get(

                    "source_type",

                    "web"

                )

        })


    # --------------------------------------------------------
    # SORT BY COMBINED SCORE
    # --------------------------------------------------------

    evidence.sort(

        key=lambda item:

            item[
                "combined_score"
            ],

        reverse=True

    )


    # --------------------------------------------------------
    # SOURCE DIVERSITY
    #
    # Only one best chunk per URL.
    # --------------------------------------------------------

    selected = []

    urls_seen = set()


    for item in evidence:

        url = item["url"]


        if not url:

            continue


        if url in urls_seen:

            continue


        selected.append(
            item
        )


        urls_seen.add(
            url
        )


        if len(selected) >= top_k:

            break


    return selected


# ============================================================
# GROUP EVIDENCE BY SOURCE
# ============================================================

def group_evidence_by_source(
    evidence
):

    grouped = {}


    for item in evidence:

        url = item["url"]


        if not url:

            continue


        if url not in grouped:

            grouped[url] = {

                "title":
                    item["title"],

                "url":
                    url,

                "trust_level":
                    item["trust_level"],

                "trust_weight":
                    item["trust_weight"],

                "best_score":
                    item["combined_score"],

                "chunks": []

            }


        grouped[url][
            "chunks"
        ].append({

            "text":
                item["text"],

            "semantic_score":
                item[
                    "semantic_score"
                ],

            "combined_score":
                item[
                    "combined_score"
                ]

        })


        if (

            item["combined_score"]

            >

            grouped[url][
                "best_score"
            ]

        ):

            grouped[url][
                "best_score"
            ] = item[
                "combined_score"
            ]


    sources = list(
        grouped.values()
    )


    sources.sort(

        key=lambda source:

            source[
                "best_score"
            ],

        reverse=True

    )


    return sources


# ============================================================
# SOURCE AGREEMENT
# ============================================================

def calculate_source_agreement(
    source_groups
):

    if not source_groups:

        return 0.0


    source_count = len(
        source_groups
    )


    total_weight = sum(

        source[
            "trust_weight"
        ]

        for source
        in source_groups

    )


    average_trust = (

        total_weight
        /
        source_count

    )


    if source_count >= 3:

        diversity_score = 1.0

    elif source_count == 2:

        diversity_score = 0.75

    else:

        diversity_score = 0.50


    agreement = (

        average_trust
        *
        diversity_score

    )


    return round(

        agreement,

        4

    )


# ============================================================
# CONVERT SOURCE OBJECTS TO JSON
# ============================================================

def source_to_dict(source):

    trust_level, trust_weight = (

        get_source_trust(
            source.url
        )

    )


    return {

        "title":
            source.title,

        "url":
            source.url,

        "snippet":
            source.snippet,

        "source_type":
            source.source_type,

        "trust_level":
            trust_level,

        "trust_weight":
            trust_weight

    }


# ============================================================
# VERIFY CLAIM
# ============================================================

def verify_claim(claim):
    print()
    print("=" * 70)
    print("VERIFYING CLAIM:")
    print(claim)
    print("=" * 70)

    complexity = determine_complexity(claim)

    sources = retrieve_sources(claim, complexity)
    print("Trusted sources found:", len(sources))

    newly_indexed_chunks = index_sources(sources)
    print("Newly indexed chunks:", newly_indexed_chunks)

    evidence = retrieve_evidence(claim, TOP_K)
    print("Qdrant evidence:", len(evidence))

    source_groups = group_evidence_by_source(evidence)
    source_agreement = calculate_source_agreement(source_groups)

    best_score = 0.0
    if evidence:
        best_score = max(item["combined_score"] for item in evidence)

    nli_result = verify_claim_against_evidence(claim, evidence)

    print()
    print("NLI RESULT:")
    print("Entailment:", nli_result["entailment"])
    print("Contradiction:", nli_result["contradiction"])
    print("Neutral:", nli_result["neutral"])
    print("Verdict:", nli_result["verdict"])

    status = nli_result["verdict"]
    indexed_chunks = len(evidence)

    # Calculate confidence based on NLI results
    if status == "SUPPORTED":
        confidence = round(nli_result["entailment"] * 100, 2)
    elif status == "CONTRADICTED":
        confidence = round(nli_result["contradiction"] * 100, 2)
    elif status == "PARTIALLY SUPPORTED":
        confidence = round(max(nli_result["entailment"], nli_result["contradiction"]) * 100, 2)
    else:
        confidence = round((1 - nli_result["neutral"]) * 100, 2)

    evidence_for_response = []
    for item in evidence:
        evidence_for_response.append({
            "semantic_score": item["semantic_score"],
            "trust_weight": item["trust_weight"],
            "combined_score": item["combined_score"],
            "trust_level": item["trust_level"],
            "text": item["text"],
            "title": item["title"],
            "url": item["url"],
            "source_type": item["source_type"]
        })

    nli_evidence = nli_result.get("evidence_details", [])

    return {
        "claim": claim,
        "status": status,
        "confidence": confidence,  # Add confidence
        "similarity_score": round(best_score, 4),
        "complexity": complexity,
        "indexed_chunks": indexed_chunks,
        "newly_indexed_chunks": newly_indexed_chunks,
        "evidence_count": len(evidence),
        "source_count": len(source_groups),
        "source_agreement": source_agreement,
        "nli": {
            "entailment": nli_result["entailment"],
            "contradiction": nli_result["contradiction"],
            "neutral": nli_result["neutral"],
            "verdict": nli_result["verdict"],
            "evidence_used": nli_result.get("evidence_used", 0),
            "evidence_ignored": nli_result.get("evidence_ignored", 0)
        },
        "evidence": evidence_for_response,
        "nli_evidence": nli_evidence,
        "source_groups": source_groups,
        "sources": [source_to_dict(source) for source in sources]
    }


# ============================================================
# ANALYZE ENDPOINT
# ============================================================

@app.post("/analyze")
def analyze_response(request: AnalyzeRequest):
    print("\n" + "=" * 70)
    print("ANALYZE REQUEST RECEIVED")
    print("=" * 70)
    print(f"Platform: {request.platform}")
    print(f"Website: {request.website}")
    print(f"Answer length: {len(request.answer)}")
    print(f"Answer preview: {request.answer[:200]}...")
    print("=" * 70)
    
    answer = clean_text(request.answer)
    
    # Extract claims
    claims = extract_claims(answer)
    
    print(f"\nProcessing {len(claims)} claims...")
    
    results = []

    for claim in claims:
        print(f"\n--- Processing Claim: {claim[:80]}... ---")
        try:
            result = verify_claim(claim)
            results.append(result)
            print(f"✅ Claim processed: {result.get('status', 'UNKNOWN')}")
        except Exception as e:
            print(f"❌ Claim verification error: {e}")
            import traceback
            traceback.print_exc()
            results.append({
                "claim": claim,
                "status": "ERROR",
                "confidence": 0,
                "similarity_score": 0.0,
                "complexity": determine_complexity(claim),
                "indexed_chunks": 0,
                "evidence_count": 0,
                "source_count": 0,
                "source_agreement": 0.0,
                "nli": {
                    "entailment": 0.0,
                    "contradiction": 0.0,
                    "neutral": 1.0,
                    "verdict": "ERROR",
                    "evidence_used": 0,
                    "evidence_ignored": 0
                },
                "evidence": [],
                "nli_evidence": [],
                "source_groups": [],
                "sources": [],
                "error": str(e)
            })

    if not results:
        print("No results to return")
        return {
            "status": "NO_CLAIMS",
            "reliability": 0,
            "total_claims": 0,
            "supported_claims": 0,
            "contradicted_claims": 0,
            "partially_supported_claims": 0,
            "insufficient_evidence_claims": 0,
            "claims": [],
            "sources": [],
            "platform": request.platform,
            "timestamp": datetime.utcnow().isoformat()
        }

    # Calculate statistics
    supported = sum(1 for result in results if result["status"] == "SUPPORTED")
    contradicted = sum(1 for result in results if result["status"] == "CONTRADICTED")
    partially_supported = sum(1 for result in results if result["status"] == "PARTIALLY SUPPORTED")
    insufficient = sum(1 for result in results if result["status"] == "INSUFFICIENT EVIDENCE")
    total = len(results)

    reliability = ((supported + partially_supported * 0.5) / total) * 100

    print("\n" + "=" * 70)
    print("ANALYSIS SUMMARY")
    print("=" * 70)
    print(f"Total claims: {total}")
    print(f"Supported: {supported}")
    print(f"Partially Supported: {partially_supported}")
    print(f"Contradicted: {contradicted}")
    print(f"Insufficient Evidence: {insufficient}")
    print(f"Reliability: {reliability:.2f}%")
    print("=" * 70)

    source_map = {}
    for result in results:
        for source in result.get("sources", []):
            url = source.get("url", "")
            if not url:
                continue
            if url not in source_map:
                source_map[url] = source

    all_sources = list(source_map.values())

    return {
        "status": "ANALYZED",
        "platform": request.platform,
        "website": request.website,
        "url": request.url,
        "timestamp": datetime.utcnow().isoformat(),
        "reliability": round(reliability, 2),
        "total_claims": total,
        "supported_claims": supported,
        "contradicted_claims": contradicted,
        "partially_supported_claims": partially_supported,
        "insufficient_evidence_claims": insufficient,
        "sources_found": len(all_sources),
        "claims": results,
        "sources": all_sources[:15]
    }

# ============================================================
# ROOT
# ============================================================

@app.get("/")
def root():

    return {

        "project":
            "Adaptive RAG AI Hallucination Detector",

        "version":
            "6.0",

        "status":
            "running",

        "rag":
            "enabled",

        "vector_database":
            "Qdrant",

        "collection":
            QDRANT_COLLECTION_NAME,

        "embedding_model":
            EMBEDDING_MODEL_NAME,

        "features": [

            "Web Search",

            "Trusted Source Filtering",

            "Web Page Extraction",

            "Paragraph Aware Chunking",

            "Local Embeddings",

            "Qdrant Vector Search",

            "Duplicate Prevention",

            "Source Trust Ranking",

            "Multi-Source Retrieval",

            "Source Diversity",

            "Source Agreement",

            "Semantic Relevance Filtering",

            "NLI Verification",

            "NLI Based Verdict"

        ]

    }


# ============================================================
# QDRANT STATUS
# ============================================================

@app.get("/qdrant-status")
def qdrant_status():

    try:

        collections = (

            qdrant
            .get_collections()

        )


        collection_names = [

            collection.name

            for collection
            in collections.collections

        ]


        return {

            "status":
                "connected",

            "collection":
                QDRANT_COLLECTION_NAME,

            "collections":
                collection_names

        }


    except Exception as e:

        return {

            "status":
                "error",

            "message":
                str(e)

        }


# ============================================================
# QDRANT INFO
# ============================================================

@app.get("/qdrant-info")
def qdrant_info():

    try:

        collection_info = (

            qdrant
            .get_collection(

                QDRANT_COLLECTION_NAME

            )

        )


        return {

            "collection":
                QDRANT_COLLECTION_NAME,

            "points_count":
                collection_info.points_count,

            "status":
                str(
                    collection_info.status
                )

        }


    except Exception as e:

        return {

            "status":
                "error",

            "message":
                str(e)

        }


# ============================================================
# RESET QDRANT
# ============================================================

@app.delete("/reset-qdrant")
def reset_qdrant():

    try:

        qdrant.delete_collection(

            QDRANT_COLLECTION_NAME

        )


        initialize_qdrant()


        return {

            "status":
                "success",

            "message":
                "Qdrant collection reset successfully",

            "collection":
                QDRANT_COLLECTION_NAME

        }


    except Exception as e:

        return {

            "status":
                "error",

            "message":
                str(e)

        }