from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import mwparserfromhell

@dataclass
class Infobox:
    template_name: str
    params: dict[str, str]

def extract_infobox_character(wikitext: str) -> Optional[Infobox]:
    code = mwparserfromhell.parse(wikitext)
    templates = code.filter_templates(recursive=True)

    chosen = None
    for tpl in templates:
        name = str(tpl.name).strip().lower().replace("_", " ")
        if "infobox character" == name or name.endswith("infobox character") or "infobox character" in name:
            chosen = tpl
            break

    if not chosen:
        return None

    template_name = str(chosen.name).strip()
    params: dict[str, str] = {}
    for p in chosen.params:
        key = str(p.name).strip()
        val = str(p.value).strip()
        if key:
            params[key] = val

    return Infobox(template_name=template_name, params=params)