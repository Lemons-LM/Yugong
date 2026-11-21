import json
import re
import sys
import urllib.request
from pathlib import Path

WIKI_API_ENV = "WIKI_API"
USER_AGENT_ENV = "USER_AGENT"
BOOKSOURCE_REALNAME = "Booksources"


def load_env(path):
    if not path.is_file():
        raise SystemExit(".env is required")

    env = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key:
            env[key] = value
    return env


def canonicalise(value):
    """Mirror canonicalise_title_fragment from isbn_template_normalise.py."""
    return "".join(ch for ch in value.strip().casefold()
                   if not ch.isspace() and ch != "_")


def main():
    env = load_env(Path(".env"))
    wiki_api = env.get(WIKI_API_ENV)
    user_agent = env.get(USER_AGENT_ENV)
    if not wiki_api or not user_agent:
        raise SystemExit(".env must define WIKI_API and USER_AGENT")

    url = (f"{wiki_api}"
           "?action=query&format=json"
           "&meta=siteinfo&siprop=specialpagealiases&formatversion=2")
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    # Always keep the software-defined realname as a canonical fallback.
    aliases = {canonicalise(BOOKSOURCE_REALNAME)}
    realname_lower = BOOKSOURCE_REALNAME.casefold()
    found_booksources = False
    for entry in data.get("query", {}).get("specialpagealiases", []) or []:
        if not isinstance(entry, dict):
            continue
        if entry.get("realname", "").casefold() != realname_lower:
            continue
        found_booksources = True
        for alias in entry.get("aliases", []) or []:
            if isinstance(alias, str) and alias:
                if canon := canonicalise(alias):
                    aliases.add(canon)
        break

    if not found_booksources:
        raise SystemExit(
            "API response has no Booksources special-page entry; "
            "refusing to overwrite the committed aliases")

    sorted_aliases = sorted(aliases)
    aliases_repr = "frozenset({" + ", ".join(
        repr(alias) for alias in sorted_aliases) + "})"

    path = Path("isbn_template_normalise.py")
    text = path.read_text(encoding="utf-8")
    new_text = re.sub(
        r"BOOKSOURCE_PAGE_ALIASES\s*=\s*frozenset\(\s*\{[^}]*\}\s*\)",
        lambda _match: f"BOOKSOURCE_PAGE_ALIASES = {aliases_repr}",
        text,
    )

    if new_text == text:
        print("BOOKSOURCE_PAGE_ALIASES is already up to date.")
        return

    path.write_text(new_text, encoding="utf-8")
    print(f"Updated BOOKSOURCE_PAGE_ALIASES: {sorted_aliases}")


if __name__ == "__main__":
    main()
