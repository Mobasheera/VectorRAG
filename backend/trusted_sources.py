from urllib.parse import urlparse


# =========================================================
# TRUSTED DOMAINS
# =========================================================

TRUSTED_DOMAINS = {

    # -----------------------------------------------------
    # Very High Trust
    # -----------------------------------------------------

    "nasa.gov": 1.00,
    "science.nasa.gov": 1.00,

    "who.int": 1.00,

    "un.org": 1.00,

    "gov": 1.00,


    # -----------------------------------------------------
    # High / Reference Trust
    # -----------------------------------------------------

    "britannica.com": 0.75,

    "wikipedia.org": 0.75,

    "nature.com": 0.90,

    "sciencedirect.com": 0.90,

    "springer.com": 0.90,

    "nih.gov": 1.00,

    "ncbi.nlm.nih.gov": 1.00,

    "ieee.org": 0.90,

    "acm.org": 0.90,

    "edu": 0.90

}


# =========================================================
# GET DOMAIN
# =========================================================

def get_domain(url):

    if not url:
        return ""

    try:

        parsed = urlparse(
            url
        )

        domain = (
            parsed.netloc
            .lower()
            .replace(
                "www.",
                ""
            )
        )

        return domain

    except Exception:

        return ""


# =========================================================
# CHECK TRUST
# =========================================================

def is_trusted(url):

    domain = get_domain(
        url
    )

    if not domain:
        return False


    # -----------------------------------------------------
    # Exact domain
    # -----------------------------------------------------

    if domain in TRUSTED_DOMAINS:

        return True


    # -----------------------------------------------------
    # Subdomain checking
    # -----------------------------------------------------

    for trusted_domain in TRUSTED_DOMAINS:

        if trusted_domain in [
            "gov",
            "edu"
        ]:

            continue


        if domain.endswith(
            "." + trusted_domain
        ):

            return True


    # -----------------------------------------------------
    # Government domains
    # -----------------------------------------------------

    if domain.endswith(
        ".gov"
    ):

        return True


    if domain.endswith(
        ".gov.in"
    ):

        return True


    # -----------------------------------------------------
    # Educational domains
    # -----------------------------------------------------

    if domain.endswith(
        ".edu"
    ):

        return True


    if domain.endswith(
        ".ac.in"
    ):

        return True


    return False


# =========================================================
# TRUST SCORE
# =========================================================

def get_trust_score(url):

    domain = get_domain(
        url
    )

    if not domain:

        return 0.0


    # -----------------------------------------------------
    # Exact match
    # -----------------------------------------------------

    if domain in TRUSTED_DOMAINS:

        return TRUSTED_DOMAINS[
            domain
        ]


    # -----------------------------------------------------
    # Subdomain match
    # -----------------------------------------------------

    for trusted_domain, score in (
        TRUSTED_DOMAINS.items()
    ):

        if trusted_domain in [
            "gov",
            "edu"
        ]:

            continue


        if domain.endswith(
            "." + trusted_domain
        ):

            return score


    # -----------------------------------------------------
    # Government
    # -----------------------------------------------------

    if domain.endswith(
        ".gov"
    ):

        return 1.00


    if domain.endswith(
        ".gov.in"
    ):

        return 1.00


    # -----------------------------------------------------
    # Education
    # -----------------------------------------------------

    if domain.endswith(
        ".edu"
    ):

        return 0.90


    if domain.endswith(
        ".ac.in"
    ):

        return 0.90


    return 0.0


# =========================================================
# SOURCE TYPE
# =========================================================

def get_source_type(url):

    domain = get_domain(
        url
    )


    if not domain:

        return "unknown"


    # -----------------------------------------------------
    # Wikipedia
    # -----------------------------------------------------

    if domain == "wikipedia.org" or domain.endswith(
        ".wikipedia.org"
    ):

        return "wikipedia"


    # -----------------------------------------------------
    # Government
    # -----------------------------------------------------

    if (
        domain.endswith(".gov")
        or domain.endswith(".gov.in")
    ):

        return "government"


    # -----------------------------------------------------
    # Education
    # -----------------------------------------------------

    if (
        domain.endswith(".edu")
        or domain.endswith(".ac.in")
    ):

        return "academic"


    # -----------------------------------------------------
    # NASA
    # -----------------------------------------------------

    if domain == "nasa.gov" or domain.endswith(
        ".nasa.gov"
    ):

        return "official"


    # -----------------------------------------------------
    # WHO
    # -----------------------------------------------------

    if domain == "who.int" or domain.endswith(
        ".who.int"
    ):

        return "official"


    # -----------------------------------------------------
    # United Nations
    # -----------------------------------------------------

    if domain == "un.org" or domain.endswith(
        ".un.org"
    ):

        return "official"


    # -----------------------------------------------------
    # Research publishers
    # -----------------------------------------------------

    if domain in [

        "nature.com",

        "sciencedirect.com",

        "springer.com",

        "ieee.org",

        "acm.org"

    ]:

        return "research"


    # -----------------------------------------------------
    # Britannica
    # -----------------------------------------------------

    if domain == "britannica.com" or domain.endswith(
        ".britannica.com"
    ):

        return "reference"


    # -----------------------------------------------------
    # Default
    # -----------------------------------------------------

    return "web_search"