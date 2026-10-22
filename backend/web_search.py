import requests

from bs4 import BeautifulSoup

from urllib.parse import (
    urlparse,
    parse_qs,
    unquote,
    quote
)

from .config import MAX_WEB_RESULTS

from .trusted_sources import (
    is_trusted,
    get_trust_score,
    get_source_type,
    get_domain
)


# =========================================================
# USER AGENT
# =========================================================

USER_AGENT = (
    "Mozilla/5.0 "
    "(Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/151.0 Safari/537.36"
)


# =========================================================
# CLEAN URL
# =========================================================

def clean_url(url):

    if not url:
        return ""

    try:

        parsed = urlparse(url)

        query = parse_qs(
            parsed.query
        )

        # DuckDuckGo redirect
        if "uddg" in query:

            return unquote(
                query["uddg"][0]
            )

        return url

    except Exception:

        return url


# =========================================================
# NORMALIZE URL
# =========================================================

def normalize_url(url):

    if not url:
        return ""

    try:

        url = clean_url(
            str(url).strip()
        )

        parsed = urlparse(url)

        if not parsed.netloc:
            return ""

        scheme = (
            parsed.scheme
            or "https"
        ).lower()

        domain = (
            parsed.netloc
            .lower()
            .replace(
                "www.",
                ""
            )
        )

        path = (
            parsed.path
            or "/"
        )

        # Remove trailing slash except root
        if path != "/":
            path = path.rstrip("/")

        return (
            scheme
            + "://"
            + domain
            + path
        )

    except Exception:

        return ""


# =========================================================
# CREATE RESULT
# =========================================================

def make_result(
    title,
    url,
    snippet=""
):

    url = normalize_url(
        url
    )

    if not url:
        return None

    if not is_trusted(url):
        return None

    trust_score = (
        get_trust_score(url)
    )

    return {

        "title":
            title or "Untitled",

        "url":
            url,

        "snippet":
            snippet or "",

        "domain":
            get_domain(url),

        "trust_score":
            float(trust_score),

        "source_type":
            get_source_type(url)

    }


# =========================================================
# PARSE DUCKDUCKGO
# =========================================================

def parse_duckduckgo_results(
    html
):

    results = []

    if not html:
        return results

    try:

        soup = BeautifulSoup(
            html,
            "html.parser"
        )

        result_blocks = soup.select(
            ".result"
        )

        for result in result_blocks:

            link = result.select_one(
                ".result__a"
            )

            if not link:
                continue

            title = link.get_text(
                " ",
                strip=True
            )

            href = clean_url(
                link.get(
                    "href",
                    ""
                )
            )

            if not href:
                continue

            snippet_element = (
                result.select_one(
                    ".result__snippet"
                )
            )

            snippet = ""

            if snippet_element:

                snippet = (
                    snippet_element.get_text(
                        " ",
                        strip=True
                    )
                )

            item = make_result(
                title,
                href,
                snippet
            )

            if item:

                results.append(
                    item
                )

    except Exception as e:

        print(
            "DuckDuckGo parsing error:",
            e
        )

    return results


# =========================================================
# DUCKDUCKGO SEARCH
# =========================================================

def search_duckduckgo(
    query
):

    if not query:
        return []

    search_url = (
        "https://html.duckduckgo.com/html/"
    )

    headers = {

        "User-Agent":
            USER_AGENT,

        "Accept":
            "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",

        "Accept-Language":
            "en-US,en;q=0.9",

        "Referer":
            "https://duckduckgo.com/"

    }

    attempts = [

        ("GET", None),

        ("POST", None),

    ]

    for method, _ in attempts:

        try:

            if method == "GET":

                response = requests.get(

                    search_url,

                    params={
                        "q": query
                    },

                    headers=headers,

                    timeout=15

                )

            else:

                response = requests.post(

                    search_url,

                    data={
                        "q": query
                    },

                    headers=headers,

                    timeout=15

                )

            print(
                "DuckDuckGo status:",
                response.status_code
            )

            print(
                "DuckDuckGo response size:",
                len(response.text)
            )

            results = (
                parse_duckduckgo_results(
                    response.text
                )
            )

            if results:

                return results

        except Exception as e:

            print(
                "DuckDuckGo request error:",
                e
            )

    return []


# =========================================================
# WIKIPEDIA FALLBACK
# =========================================================

def search_wikipedia(
    query
):

    results = []

    if not query:
        return results

    try:

        response = requests.get(

            "https://en.wikipedia.org/w/api.php",

            params={

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

            },

            headers={

                "User-Agent":
                    "VectorRAG/1.0"

            },

            timeout=15

        )

        response.raise_for_status()

        data = response.json()

        search_results = (
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

        for item in search_results:

            title = item.get(
                "title",
                ""
            )

            if not title:
                continue

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
                " ",
                strip=True
            )

            result = make_result(

                "Wikipedia - "
                + title,

                page_url,

                snippet

            )

            if result:

                result[
                    "source_type"
                ] = "wikipedia"

                results.append(
                    result
                )

    except Exception as e:

        print(
            "Wikipedia search error:",
            e
        )

    return results


# =========================================================
# DEDUPLICATE
# =========================================================

def deduplicate_results(
    results
):

    unique = []

    seen = set()

    for item in results:

        url = normalize_url(
            item.get(
                "url",
                ""
            )
        )

        if not url:
            continue

        if url in seen:
            continue

        seen.add(url)

        item["url"] = url

        # Repair metadata
        item["domain"] = (
            item.get(
                "domain"
            )
            or
            get_domain(url)
        )

        item["trust_score"] = float(
            item.get(
                "trust_score",
                get_trust_score(url)
            )
        )

        item["source_type"] = (
            item.get(
                "source_type"
            )
            or
            get_source_type(url)
        )

        unique.append(
            item
        )

    return unique


# =========================================================
# SEARCH WEB
# =========================================================

def search_web(
    query
):

    """
    Search the public web.

    Existing features preserved:

    - DuckDuckGo search
    - Trusted source filtering
    - Trust score
    - Source type
    - Domain
    - Duplicate removal
    - Maximum result limit
    - Wikipedia fallback
    """

    print()
    print("=" * 60)
    print("WEB SEARCH")
    print("=" * 60)

    print(
        "Query:",
        query
    )

    results = []

    # -----------------------------------------------------
    # STEP 1 - DUCKDUCKGO
    # -----------------------------------------------------

    ddg_results = (
        search_duckduckgo(
            query
        )
    )

    results.extend(
        ddg_results
    )

    # -----------------------------------------------------
    # STEP 2 - WIKIPEDIA FALLBACK
    #
    # If DuckDuckGo is blocked or returns no usable
    # trusted results, Wikipedia provides a trusted
    # reference source.
    # -----------------------------------------------------

    if not results:

        print(
            "DuckDuckGo returned no usable results."
        )

        print(
            "Using Wikipedia fallback..."
        )

        results.extend(
            search_wikipedia(
                query
            )
        )

    # -----------------------------------------------------
    # STEP 3 - DEDUPLICATE
    # -----------------------------------------------------

    results = (
        deduplicate_results(
            results
        )
    )

    # -----------------------------------------------------
    # STEP 4 - TRUST FILTER
    # -----------------------------------------------------

    results = [

        item

        for item in results

        if (
            is_trusted(
                item.get(
                    "url",
                    ""
                )
            )
            and
            float(
                item.get(
                    "trust_score",
                    0.0
                )
            ) >= 0.70
        )

    ]

    # -----------------------------------------------------
    # STEP 5 - SORT
    #
    # Trust first, then source type.
    # -----------------------------------------------------

    source_priority = {

        "official": 5,

        "government": 5,

        "research": 4,

        "academic": 3,

        "reference": 2,

        "wikipedia": 2,

        "web_search": 1

    }

    results.sort(

        key=lambda item: (

            float(
                item.get(
                    "trust_score",
                    0.0
                )
            ),

            source_priority.get(

                item.get(
                    "source_type",
                    ""
                ),

                0

            )

        ),

        reverse=True

    )

    results = results[
        :MAX_WEB_RESULTS
    ]

    print(
        "Trusted results:",
        len(results)
    )

    for index, item in enumerate(
        results,
        start=1
    ):

        print()
        print(
            "Result",
            index
        )

        print(
            "Title:",
            item.get(
                "title",
                ""
            )
        )

        print(
            "Domain:",
            item.get(
                "domain",
                ""
            )
        )

        print(
            "Trust:",
            item.get(
                "trust_score",
                0
            )
        )

        print(
            "URL:",
            item.get(
                "url",
                ""
            )
        )

    print("=" * 60)

    return results