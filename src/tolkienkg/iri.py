from urllib.parse import quote
from .config import BASE_URI

def slugify(title: str) -> str:
    """
    Conservative slugification:
    - strip
    - spaces -> underscores
    - percent-encode non-safe chars
    """
    t = (title or "").strip().replace(" ", "_")
    # keep underscores and common safe chars
    return quote(t, safe="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~:")

def page_iri(title: str) -> str:
    return f"{BASE_URI}/page/{slugify(title)}"

def resource_iri(title: str) -> str:
    return f"{BASE_URI}/resource/{slugify(title)}"