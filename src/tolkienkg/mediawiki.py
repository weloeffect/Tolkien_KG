from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from .config import USER_AGENT, REQUEST_TIMEOUT_S, REQUEST_SLEEP_S, TOLKIEN_GATEWAY_API

@dataclass
class MediaWikiClient:
    api_url: str = TOLKIEN_GATEWAY_API
    session: requests.Session = requests.Session()

    def __post_init__(self) -> None:
        self.session.headers.update({"User-Agent": USER_AGENT})

    def get(self, params: dict[str, Any]) -> dict[str, Any]:
        time.sleep(REQUEST_SLEEP_S)
        r = self.session.get(self.api_url, params=params, timeout=REQUEST_TIMEOUT_S)
        r.raise_for_status()
        return r.json()

    def fetch_wikitext_parse(self, title: str) -> str:
        """
        Uses action=parse to get wikitext of a page (with redirects resolved).
        """
        data = self.get({
            "action": "parse",
            "page": title,
            "prop": "wikitext",
            "redirects": 1,
            "format": "json",
        })
        if "error" in data:
            raise RuntimeError(f"MediaWiki API error for {title}: {data['error']}")
        return data["parse"]["wikitext"]["*"]

    def list_category_members(self, category_title: str, namespace: int = 0, limit: int = 500) -> list[str]:
        """
        Return up to `limit` titles from a category, restricted to a namespace.
        Uses pagination via cmcontinue.
        """
        if not category_title.startswith("Category:"):
            category_title = "Category:" + category_title

        titles: list[str] = []
        cmcontinue: str | None = None

        while True:
            remaining = limit - len(titles)
            if remaining <= 0:
                break

            params: dict[str, Any] = {
                "action": "query",
                "list": "categorymembers",
                "cmtitle": category_title,
                "cmnamespace": str(namespace),
                # use up to 500 per request (MediaWiki typical cap)
                "cmlimit": str(min(500, remaining)),
                "format": "json",
            }
            if cmcontinue:
                params["cmcontinue"] = cmcontinue

            data = self.get(params)
            members = data.get("query", {}).get("categorymembers", [])
            titles.extend([m["title"] for m in members if "title" in m])

            cmcontinue = data.get("continue", {}).get("cmcontinue")
            if not cmcontinue:
                break

        return titles

    def list_embeddedin(self, template_title: str, namespace: int = 0, limit: int = 500) -> list[str]:
        """
        Return up to `limit` page titles that embed a given template.
        Uses pagination via eicontinue.
        """
        if not template_title.startswith("Template:"):
            template_title = "Template:" + template_title

        titles: list[str] = []
        eicontinue: str | None = None

        while True:
            remaining = limit - len(titles)
            if remaining <= 0:
                break

            params: dict[str, Any] = {
                "action": "query",
                "list": "embeddedin",
                "eititle": template_title,
                "einamespace": str(namespace),
                "eilimit": str(min(500, remaining)),
                "format": "json",
            }
            if eicontinue:
                params["eicontinue"] = eicontinue

            data = self.get(params)
            pages = data.get("query", {}).get("embeddedin", [])
            titles.extend([p["title"] for p in pages if "title" in p])

            eicontinue = data.get("continue", {}).get("eicontinue")
            if not eicontinue:
                break

        return titles
    

    def list_all_pages(self, namespace: int = 0, limit: int | None = None) -> list[str]:
        """
        Exhaustively list page titles using action=query&list=allpages.
        Handles pagination via apcontinue.

        namespace=0 -> main namespace.
        limit=None -> no limit (true exhaustive crawl).
        """
        titles: list[str] = []
        apcontinue: str | None = None

        while True:
            # how many we can still fetch in this loop
            if limit is None:
                batch_size = 500
            else:
                remaining = limit - len(titles)
                if remaining <= 0:
                    break
                batch_size = min(500, remaining)

            params: dict[str, Any] = {
                "action": "query",
                "list": "allpages",
                "apnamespace": str(namespace),
                "aplimit": str(batch_size),
                "format": "json",
            }
            if apcontinue:
                params["apcontinue"] = apcontinue

            data = self.get(params)
            pages = data.get("query", {}).get("allpages", [])
            titles.extend([p["title"] for p in pages if "title" in p])

            apcontinue = data.get("continue", {}).get("apcontinue")
            if not apcontinue:
                break

        return titles

class WikitextCache:
    def __init__(self, cache_dir: str = "data/cache/wikitext") -> None:
        self.dir = Path(cache_dir)
        self.dir.mkdir(parents=True, exist_ok=True)

    def path_for(self, title: str) -> Path:
        safe = title.replace("/", "_")
        return self.dir / f"{safe}.wiki"

    def get_or_fetch(self, client: MediaWikiClient, title: str) -> str:
        p = self.path_for(title)
        if p.exists():
            return p.read_text(encoding="utf-8")
        txt = client.fetch_wikitext_parse(title)
        p.write_text(txt, encoding="utf-8")
        return txt