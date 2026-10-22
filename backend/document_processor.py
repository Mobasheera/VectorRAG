import re
import requests

from bs4 import BeautifulSoup

from .config import (
    CHUNK_SIZE,
    CHUNK_OVERLAP
)


USER_AGENT = (
    "Mozilla/5.0 "
    "(Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/151.0 Safari/537.36"
)


def clean_text(text):

    if not text:
        return ""

    # REMOVE ALL EMOJIS AND NON-ASCII CHARACTERS
    # This is the core fix to stop the "Hallucination" errors on bulleted lists
    text = re.sub(r'[^\x00-\x7F]+', ' ', text) 

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


def fetch_webpage(url):

    try:

        response = requests.get(
            url,
            headers={
                "User-Agent": USER_AGENT
            },
            timeout=15
        )

        response.raise_for_status()

        return response.text

    except Exception as e:

        print(
            "Page download error:",
            url,
            e
        )

        return ""


def extract_main_text(html):

    if not html:
        return ""

    soup = BeautifulSoup(
        html,
        "lxml"
    )

    # Remove unnecessary elements
    for tag in soup([
        "script",
        "style",
        "noscript",
        "svg",
        "nav",
        "footer",
        "header",
        "form",
        "aside"
    ]):

        tag.decompose()

    # Prefer article/main
    main = (
        soup.find("article")
        or soup.find("main")
        or soup.body
    )

    if not main:
        return ""

    text = main.get_text(
        " ",
        strip=True
    )

    return clean_text(text)


def chunk_text(
    text,
    chunk_size=CHUNK_SIZE,
    overlap=CHUNK_OVERLAP
):

    text = clean_text(text)

    if not text:
        return []

    if overlap >= chunk_size:

        raise ValueError(
            "Overlap must be smaller "
            "than chunk size."
        )

    # =========================================================
    # NEW: SPLIT BY NEWLINES FIRST (Preserves Bullet Points)
    # =========================================================
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]

    chunks = []
    current_chunk = ""
    current_word_count = 0
    max_words = int(chunk_size / 6)  # Rough estimate of words in a chunk

    for paragraph in paragraphs:
        p_words = len(paragraph.split())

        if p_words > max_words:
            # If a single paragraph is too big, save current and split it
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = ""
                current_word_count = 0
            
            # Split the long paragraph by period
            sentences = re.split(r'(?<=[.!?])\s+', paragraph)
            for sentence in sentences:
                s_words = len(sentence.split())
                if current_word_count + s_words > max_words:
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                    current_chunk = sentence
                    current_word_count = s_words
                else:
                    current_chunk += " " + sentence
                    current_word_count += s_words
            continue

        # Add paragraph to current chunk
        if current_word_count + p_words > max_words:
            chunks.append(current_chunk.strip())
            current_chunk = paragraph
            current_word_count = p_words
        else:
            current_chunk += " " + paragraph
            current_word_count += p_words

    if current_chunk:
        chunks.append(current_chunk.strip())

    # =========================================================
    # ADD OVERLAP
    # =========================================================
    final_chunks = []
    for i, chunk in enumerate(chunks):
        if i > 0 and overlap > 0:
            prev_chunk = chunks[i-1]
            # Add the tail of the previous chunk to the start of the current one
            overlap_text = prev_chunk[-overlap:]
            final_chunks.append((overlap_text + " " + chunk).strip())
        else:
            final_chunks.append(chunk)

    return final_chunks


def process_url(url):

    html = fetch_webpage(
        url
    )

    if not html:

        return []

    text = extract_main_text(
        html
    )

    if not text:

        return []

    return chunk_text(
        text
    )