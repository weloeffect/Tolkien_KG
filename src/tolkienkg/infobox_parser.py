from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import mwparserfromhell

@dataclass
class Infobox:
    template_name: str
    params: dict[str, str]

def parse_infobox_from_file(path: str | Path) -> Infobox:
    text = Path(path).read_text(encoding="utf-8")
    code = mwparserfromhell.parse(text)

    templates = code.filter_templates()
    if not templates:
        raise ValueError("No template found in file (expected {{infobox character|...}}).")

    # Expect the first template to be the infobox
    tpl = templates[0]
    template_name = str(tpl.name).strip()

    params: dict[str, str] = {}
    for p in tpl.params:
        key = str(p.name).strip()
        value = str(p.value).strip()
        if key:
            params[key] = value

    return Infobox(template_name=template_name, params=params)