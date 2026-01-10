from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

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

    def list_category_members(self, category_title: str, limit: int = 500) -> Iterator[str]:
        """
        category_title example: 'Category:Third Age characters'
        """
        cmcontinue: str | None = None

        while True:
            params: dict[str, Any] = {
                "action": "query",
                "list": "categorymembers",
                "cmtitle": category_title,
                "cmlimit": limit,
                "cmnamespace": 0,  # main namespace pages
                "format": "json",
            }
            if cmcontinue:
                params["cmcontinue"] = cmcontinue

            data = self.get(params)
            cms = data.get("query", {}).get("categorymembers", [])
            for item in cms:
                title = item.get("title")
                if title:
                    yield title

            cont = data.get("continue", {})
            cmcontinue = cont.get("cmcontinue")
            if not cmcontinue:
                break

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