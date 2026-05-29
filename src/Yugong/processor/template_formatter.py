import toml

from src.Yugong.models.wikitext import Wikitext
from src.Yugong.utils.check_same_website import check_same_website
from src.Yugong.utils.path_helper import PROJECT_ROOT
import mwparserfromhell as mph
## TODO: Write this file. Basically want to make it apply all the rules in [/template_rules](/template_rules)'s TOMLs
##       We've designed a example toml already

def format_template(wikitext: Wikitext) -> None:
    code: mph.wikicode.Wikicode = wikitext.wikitext
    for template in code.filter_templates():
        raw_name = _safe_capitalize(template.name)
        rule = RULES.get(raw_name)
        if rule:
            apply_template_rule(template=template, rule=rule)

def apply_template_rule(template: mph.wikicode.Template, rule: dict) -> None:
    # TODO: Finish this
    pass

def _safe_capitalize(text):
    if not text:
        return
    if text[0].isalpha() and text[0].isupper():
        return text
    if not text[0].isalpha():
        return text
    text = text.strip()
    return text[0].upper() + text[1:]

def get_ruleset():
    def add_rule(json_rule: dict, file_name: str):
        print("Apply rule: ", file_name)
        print("Introduction: ", json_rule["introduction"])
        for name in json_rule["names"]:
            if name:
                RULES[_safe_capitalize(name)] = {
                    "file_name": file_name,
                    "template_level": json_rule["template_level"],
                    "params": json_rule["params"],
                }
    for file in PROJECT_ROOT.glob("template_rules/*.toml"):
        rule = toml.load(file)
        rule["file_name"] = file.name
        if rule["apply_websites"]:
            for website in rule["apply_websites"]:
                if check_same_website(website):
                    add_rule(rule, file.name)
            continue
        else:
            add_rule(rule, file.name)


RULES = {}