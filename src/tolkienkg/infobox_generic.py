import mwparserfromhell

def extract_infobox(wikitext: str, template_title: str):
    """
    Extracts the first occurrence of a given infobox template (case-insensitive).
    Returns a dict {param: value}.
    """
    if not wikitext:
        return {}

    parsed = mwparserfromhell.parse(wikitext)
    template_name = template_title.replace("Template:", "").strip().lower().replace(" ", "_")

    for template in parsed.filter_templates():
        name = str(template.name).strip().lower().replace(" ", "_")
        if name.endswith(template_name):
            info = {}
            for param in template.params:
                key = str(param.name).strip().lower().replace(" ", "_")
                value = str(param.value).strip()
                info[key] = value
            return info

    return {}