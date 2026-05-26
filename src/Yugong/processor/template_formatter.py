import toml

from src.Yugong.models.wikitext import Wikitext
from src.Yugong.utils.check_same_website import check_same_website
from src.Yugong.utils.path_helper import PROJECT_ROOT
import mwparserfromhell as mph
## TODO: Write this file. Basically want to make it apply all the rules in [/template_rules](/template_rules)'s TOMLs
##       We've designed a example toml already

def format_template(wikitext: Wikitext) -> None:
    for file in PROJECT_ROOT.glob("template_rules/*.toml"):
        rule = toml.load(file)
        apply = False
        if rule["apply_websites"]:
            for website in rule["apply_websites"]:
                if check_same_website(website):
                    apply = True
                    break
        else:
            apply = True
        if not apply:
            continue

        wikicode = mph.parse(wikitext.wikitext)
        templates = wikicode.filter_templates()
        for name in rule["names"]:
            pass
        #TODO: New Arch: First load all rules as a ruleset and a list, then apply them if match list