import toml

from src.Yugong.core.wikitext import Wikitext
from src.Yugong.utilities.check_same_website import check_same_website
from src.Yugong.utilities.path_helper import PROJECT_ROOT
import mwparserfromhell as mph

class TemplateFormatter:
    """
    Template formatter
    """
    RULES = {}
    def __init__(self):
        pass

    def format_template(self, wikitext: Wikitext) -> None:
        code: mph.wikicode.Wikicode = wikitext.wikitext
        for template in list(code.filter_templates()):
            raw_name = self._safe_capitalize(template.name)
            rule = self.RULES.get(raw_name)
            if rule:
                self.apply_template_rule(code=code, template=template, rule=rule)

    def apply_template_rule(self, code: mph.wikicode.Wikicode, template: mph.wikicode.Template, rule: dict) -> None:
        template_level = rule["template_level"]

        if template_level.get("delete"):
            code.remove(template)
            return

        if template_level.get("replace"):
            replace_str = template_level["replace"]
            new_code = mph.parse(replace_str)

            def resolve_argument(wiki_node):
                if not isinstance(wiki_node, mph.nodes.Argument):
                    return None

                param_name = str(wiki_node.name).strip()

                try:
                    param = template.get(param_name)
                    return str(param.value).strip()

                except ValueError:
                    if wiki_node.default is not None:
                        default_code = mph.parse(str(wiki_node.default))
                        for child in list(
                                default_code.ifilter_arguments(recursive=True)
                        ):
                            result = resolve_argument(child)
                            if result is not None:
                                default_code.replace(child, result)
                        return str(default_code)
                    return str(wiki_node)

            for node in list(new_code.ifilter_arguments(recursive=True)):
                resolved = resolve_argument(node)
                if resolved is not None:
                    new_code.replace(node, mph.parse(resolved))

            code.replace(template, new_code)
            return


        if template_level.get("rename") and rule["names"]:
            template.name = rule["names"][0]

        params_config = rule.get("params", [])
        for param_config in params_config:
            self.apply_param_rule(template, param_config)

    @staticmethod
    def apply_param_rule(template: mph.wikicode.Template, param_config: dict) -> None:
        param_names = param_config.get("names", [])
        if not param_names:
            return

        import re

        params_to_remove = []
        for param in list(template.params):
            param_name = str(param.name).strip()

            matched = False
            for name_pattern in param_names:
                if re.fullmatch(name_pattern, param_name):
                    matched = True
                    break

            if not matched:
                continue

            if param_config.get("delete"):
                params_to_remove.append(param)
                continue

            if param_config.get("rename") and param_config.get("new_name"):
                param.name = param_config["new_name"]

            match_configs = param_config.get("match", [])
            if match_configs:
                for match_config in match_configs:
                    condition = match_config.get("condition", "")
                    mode = match_config.get("mode", True)
                    match_replacement = match_config.get("match", "")
                    replacement = match_config.get("replacement", "")

                    if condition:
                        param_value = str(param.value).strip()
                        should_apply = bool(re.search(condition, param_value)) == mode

                        if should_apply:
                            if match_replacement and replacement:
                                new_value = re.sub(match_replacement, replacement, param_value)
                                param.value = new_value
                            elif replacement:
                                param.value = replacement

        for param in params_to_remove:
            template.remove(param)

    @staticmethod
    def _safe_capitalize(text):
        if not text:
            return
        text = text.strip()
        if text[0].isalpha() and text[0].isupper():
            return text
        if not text[0].isalpha():
            return text
        return text[0].upper() + text[1:]

    def get_ruleset(self):
        def add_rule(json_rule: dict, file_name: str):
            print("Apply rule: ", file_name)
            print("Introduction: ", json_rule["introduction"])
            for name in json_rule["names"]:
                if name:
                    self._register_rule(
                        name,
                        {
                            "file_name": file_name,
                            "template_level": json_rule.get("template_level", {}),
                            "params": json_rule.get("params", []),
                        },
                    )
        for file in PROJECT_ROOT.glob("template_rules/*.toml"):
            rule = toml.load(file)
            rule["file_name"] = file.name
            apply_websites = rule.get("apply_websites", [])
            if apply_websites:
                for website in rule["apply_websites"]:
                    if check_same_website(website):
                        add_rule(rule, file.name)
                continue
            else:
                add_rule(rule, file.name)

    def _register_rule(self, name: str, rule: dict):
        key = self._safe_capitalize(name)

        if key in self.RULES:
            raise ValueError(
                f"Duplicate template rule: '{key}' "
                f"({self.RULES[key]['file_name']} vs {rule['file_name']})"
            )

        self.RULES[key] = rule

formatter: TemplateFormatter = TemplateFormatter()