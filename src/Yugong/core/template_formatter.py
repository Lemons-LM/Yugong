"""TOML-driven template transformation rules.

Rules live in ``template_rules/*.toml`` and are loaded by
:meth:`TemplateFormatter.get_ruleset`.  :meth:`TemplateFormatter.format_template`
is the processing step that :mod:`src.Yugong.processor.do_jobs` runs on every
page — without it the rules would be loaded and printed but never applied.
"""

from __future__ import annotations

import re
from typing import Any

import mwparserfromhell as mph
import toml
from mwparserfromhell.nodes.extras import Parameter

from src.Yugong.core.logger import logger
from src.Yugong.core.settings import settings
from src.Yugong.core.wikitext import Wikitext
from src.Yugong.utilities.check_same_website import check_same_website
from src.Yugong.utilities.path_helper import PROJECT_ROOT


class TemplateFormatter:
    """Applies template rules to the templates found on a page."""

    RULES: dict[str, dict[str, Any]] = {}

    #: Whether :meth:`get_ruleset` has run at least once.
    loaded: bool = False

    def format_template(self, wikitext: Wikitext) -> None:
        """Apply every matching rule to every template on the page."""
        code = wikitext.wikitext
        if code is None:
            return

        for template in list(code.filter_templates()):
            rule = self.RULES.get(self._safe_capitalize(str(template.name)))
            if rule:
                self.apply_template_rule(code=code, template=template, rule=rule)

    def apply_template_rule(
        self,
        code: mph.wikicode.Wikicode,
        template: mph.wikicode.Template,
        rule: dict[str, Any],
    ) -> None:
        """Apply one rule to one template."""
        template_level: dict[str, Any] = rule.get("template_level", {})
        names: list[str] = rule.get("names", [])

        # ``filter_templates()`` returns nested templates too.  Removing an
        # outer template detaches the inner ones, and mwparserfromhell raises
        # ValueError when a detached node is removed/replaced.  Skip those.
        if template_level.get("delete"):
            if self._still_attached(code, template):
                code.remove(template)
            return

        if template_level.get("replace"):
            if self._still_attached(code, template):
                code.replace(
                    template,
                    self._render_replacement(template, template_level["replace"]),
                )
            return

        if template_level.get("rename") and names and settings.overwrite_template_name:
            template.name = names[0]

        for param_config in rule.get("params", []):
            self.apply_param_rule(template, param_config)

    @staticmethod
    def _still_attached(
        code: mph.wikicode.Wikicode, template: mph.wikicode.Template
    ) -> bool:
        """Return whether *template* is still part of *code*'s tree."""
        return any(node is template for node in code.filter_templates())

    @staticmethod
    def _argument_attached(code: mph.wikicode.Wikicode, node: mph.nodes.Node) -> bool:
        """Return whether *node* is still part of *code*'s argument tree."""
        return any(candidate is node for candidate in code.ifilter_arguments(recursive=True))

    @staticmethod
    def _render_replacement(template: mph.wikicode.Template, replacement: str) -> mph.wikicode.Wikicode:
        """Expand ``{{{name|default}}}`` placeholders against *template*."""
        new_code = mph.parse(replacement)

        def resolve_argument(wiki_node: mph.nodes.Node, depth: int = 0) -> str | None:
            if not isinstance(wiki_node, mph.nodes.Argument):
                return None
            if depth > 20:
                raise ValueError(
                    "replacement template nesting is too deep (possible cycle)"
                )

            param_name = str(wiki_node.name).strip()
            try:
                return str(template.get(param_name).value).strip()
            except ValueError:
                if wiki_node.default is None:
                    return str(wiki_node)

                default_code = mph.parse(str(wiki_node.default))
                for child in list(default_code.ifilter_arguments(recursive=True)):
                    # Replacing an outer argument detaches the arguments nested
                    # inside its default; skip those from the snapshot.
                    if not TemplateFormatter._argument_attached(default_code, child):
                        continue
                    resolved = resolve_argument(child, depth + 1)
                    if resolved is not None:
                        default_code.replace(child, mph.parse(resolved))
                return str(default_code)

        for node in list(new_code.ifilter_arguments(recursive=True)):
            if not TemplateFormatter._argument_attached(new_code, node):
                continue
            resolved = resolve_argument(node)
            if resolved is not None:
                new_code.replace(node, mph.parse(resolved))

        return new_code

    @staticmethod
    def apply_param_rule(template: mph.wikicode.Template, param_config: dict[str, Any]) -> None:
        """Apply one ``[[params]]`` block to a template."""
        name_patterns: list[str] = param_config.get("names", [])
        if not name_patterns:
            return

        params_to_remove = []
        for param in list(template.params):
            param_name = str(param.name).strip()
            if not any(re.fullmatch(pattern, param_name) for pattern in name_patterns):
                continue

            if param_config.get("delete"):
                params_to_remove.append(param)
                continue

            if param_config.get("rename") and param_config.get("new_name"):
                if settings.overwrite_para_name:
                    param.name = str(param_config["new_name"])

            for match_config in param_config.get("match", []):
                TemplateFormatter._apply_match_rule(param, match_config)

        for param in params_to_remove:
            template.remove(param)

    @staticmethod
    def _apply_match_rule(param: Parameter, match_config: dict[str, Any]) -> None:
        condition = str(match_config.get("condition", ""))
        mode = bool(match_config.get("mode", True))
        match_pattern = str(match_config.get("match", ""))
        replacement = str(match_config.get("replacement", ""))

        if not condition:
            return

        param_value = str(param.value).strip()
        should_apply = bool(re.search(condition, param_value)) == mode
        if not should_apply:
            return

        if match_pattern and replacement:
            # ``re.sub`` on a pattern that can match the empty string (the
            # documented ``match = ".*"``) fires twice: once for the whole value
            # and once for the empty match at the end, yielding "deaddead".
            # When the pattern covers the whole value, expand it directly.
            whole = re.fullmatch(match_pattern, param_value)
            if whole is not None:
                param.value = whole.expand(replacement)
            else:
                param.value = re.sub(match_pattern, replacement, param_value)
        elif replacement:
            param.value = replacement

    @staticmethod
    def _safe_capitalize(text: str) -> str:
        """MediaWiki treats the first letter of a title case-insensitively."""
        text = text.strip()
        if not text or not text[0].isalpha():
            return text
        return text[0].upper() + text[1:]

    # ── Rule loading ──────────────────────────────────────────────────

    def get_ruleset(self) -> None:
        """(Re)load every ``template_rules/*.toml`` file into :attr:`RULES`.

        Rules that do not apply to the configured wiki are skipped; malformed
        rules abort the run with a descriptive error instead of being ignored.
        """
        self.RULES.clear()

        for file in sorted(PROJECT_ROOT.glob("template_rules/*.toml")):
            rule: dict[str, Any] = toml.load(file)
            rule["file_name"] = file.name

            apply_websites: list[str] = rule.get("apply_websites", []) or []
            # Validate before iterating: a bare string would otherwise be
            # iterated character by character and silently skip the rule.
            if not isinstance(apply_websites, list) or not all(
                isinstance(site, str) for site in apply_websites
            ):
                raise ValueError(
                    f"Template rule {file.name} has an invalid 'apply_websites' "
                    "entry: expected a list of domain strings."
                )
            if apply_websites and not any(check_same_website(site) for site in apply_websites):
                logger.info(f"Skipping rule {file.name}: does not apply to this wiki")
                continue

            self._add_rule(rule, file.name)

        self.loaded = True

    def ensure_ruleset(self) -> None:
        """Load the rules once.

        The processing loop calls this so that ``do_jobs()`` applies the rules
        even when it is invoked without the interactive ``confirm_settings()``
        step, while a normal run does not load and print them twice.
        """
        if not self.loaded:
            self.get_ruleset()

    def _add_rule(self, rule: dict[str, Any], file_name: str) -> None:
        raw_names = rule.get("names", [])
        if not isinstance(raw_names, list) or not all(
            isinstance(name, str) for name in raw_names
        ):
            raise ValueError(
                f"Template rule {file_name}: 'names' must be a list of strings."
            )
        names: list[str] = [name for name in raw_names if name]
        if not names:
            raise ValueError(f"Template rule {file_name} has no usable 'names' entry.")
        if not isinstance(rule.get("introduction"), str) or not rule["introduction"].strip():
            raise ValueError(f"Template rule {file_name} is missing 'introduction'.")

        apply_websites = rule.get("apply_websites", []) or []
        if not isinstance(apply_websites, list) or not all(
            isinstance(site, str) for site in apply_websites
        ):
            raise ValueError(
                f"Template rule {file_name} has an invalid 'apply_websites' entry: "
                "expected a list of domain strings."
            )

        template_level: dict[str, Any] = rule.get("template_level", {}) or {}
        self._validate_template_level(template_level, file_name)

        params = rule.get("params", []) or []
        self._validate_params(params, file_name)

        print(f"Apply rule: {file_name}")
        print(f"Introduction: {rule['introduction']}")

        entry = {
            "file_name": file_name,
            "names": names,
            "template_level": template_level,
            "params": params,
        }
        for name in names:
            self._register_rule(str(name), entry)

    @staticmethod
    def _validate_template_level(template_level: dict[str, Any], file_name: str) -> None:
        if not isinstance(template_level, dict):
            raise ValueError(
                f"Template rule {file_name}: [template_level] must be a table."
            )
        for key in ("delete", "rename"):
            if key in template_level and not isinstance(template_level[key], bool):
                raise ValueError(
                    f"Template rule {file_name}: template_level.{key} must be a boolean."
                )
        if "replace" in template_level and not isinstance(template_level["replace"], str):
            raise ValueError(
                f"Template rule {file_name}: template_level.replace must be a string."
            )

        actions = [key for key in ("delete", "replace", "rename") if template_level.get(key)]
        if len(actions) > 1:
            raise ValueError(
                f"Template rule {file_name} sets conflicting [template_level] actions "
                f"{actions}: use exactly one of rename/delete/replace."
            )

    @staticmethod
    def _validate_regex(pattern: Any, where: str) -> None:
        """Fail at load time when a rule contains an unusable regex."""
        try:
            re.compile(str(pattern))
        except re.error as exc:
            raise ValueError(f"{where}: invalid regular expression {pattern!r}: {exc}") from exc

    @classmethod
    def _validate_params(cls, params: Any, file_name: str) -> None:
        """Validate every ``[[params]]`` block before any page is processed."""
        if not isinstance(params, list):
            raise ValueError(f"Template rule {file_name}: 'params' must be a list.")
        for index, param_config in enumerate(params):
            where = f"Template rule {file_name}, params[{index}]"
            if not isinstance(param_config, dict):
                raise ValueError(f"{where}: must be a table.")

            patterns = param_config.get("names", []) or []
            if not isinstance(patterns, list) or not all(
                isinstance(pattern, str) for pattern in patterns
            ):
                raise ValueError(f"{where}: 'names' must be a list of strings.")
            for pattern in patterns:
                cls._validate_regex(pattern, where)

            for key in ("rename", "delete"):
                if key in param_config and not isinstance(param_config[key], bool):
                    raise ValueError(f"{where}: '{key}' must be a boolean.")
            if "new_name" in param_config and not isinstance(param_config["new_name"], str):
                raise ValueError(f"{where}: 'new_name' must be a string.")

            if param_config.get("rename") and not param_config.get("new_name"):
                raise ValueError(f"{where}: rename = true requires 'new_name'.")
            if param_config.get("rename") and param_config.get("delete"):
                raise ValueError(f"{where}: rename and delete cannot both be true.")

            matches = param_config.get("match", []) or []
            if not isinstance(matches, list):
                raise ValueError(f"{where}: 'match' must be a list of tables.")
            for match_index, match_config in enumerate(matches):
                match_where = f"{where}.match[{match_index}]"
                if not isinstance(match_config, dict):
                    raise ValueError(f"{match_where}: must be a table.")
                if "mode" in match_config and not isinstance(match_config["mode"], bool):
                    raise ValueError(f"{match_where}: 'mode' must be a boolean.")
                for key in ("condition", "match", "replacement"):
                    if key in match_config and not isinstance(match_config[key], str):
                        raise ValueError(f"{match_where}: '{key}' must be a string.")
                if not match_config.get("condition"):
                    raise ValueError(
                        f"{match_where}: 'condition' is required; an empty "
                        "condition would silently never match."
                    )
                cls._validate_regex(match_config["condition"], match_where)
                if match_config.get("match"):
                    cls._validate_regex(match_config["match"], match_where)

    def _register_rule(self, name: str, rule: dict[str, Any]) -> None:
        key = self._safe_capitalize(name)
        if not key:
            raise ValueError(f"Template rule {rule['file_name']} has an empty name entry.")

        if key in self.RULES:
            raise ValueError(
                f"Duplicate template rule: '{key}' "
                f"({self.RULES[key]['file_name']} vs {rule['file_name']})"
            )

        self.RULES[key] = rule


formatter: TemplateFormatter = TemplateFormatter()
