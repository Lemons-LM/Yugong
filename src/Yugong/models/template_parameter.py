from src.Yugong.utils.is_empty_or_none import is_str_empty_or_none, is_list_empty_or_none, is_int_lt_or_none


#NOTE: Note that if a template is like {{Foo|test=test|bar}}, it will also regard "bar" as position para 1
# TODO: This class has some errs on type and syntax, like name=None?str? and the testing logic
# TODO: Make the anonymous paras available for lua templates
class TemplateParameter:
    """
    A class used to represent a template parameter with various validation and initialization options.

    Attributes:
        name (str): The name of the parameter. Defaults to None.
        position (int): The position of the parameter in the template. Defaults to None.
        alias (list[str]): A list of aliases for the parameter. Defaults to None.
        required (bool): Indicates whether the parameter is required. Defaults to False.
        regex_lookup_pattern (str): Regex pattern used for lookup operations. Defaults to None.
        regex_format_pattern (str): Regex pattern used for formatting operations. Defaults to None.
        regex_multiline_mode (bool): Enables multiline mode for regex patterns. Defaults to False.
        remove_para (bool): Indicates whether the parameter should be removed. Defaults to False.
        is_patterned_para (bool): Defines if it is a para with pattern-like, for lua template usages. Defaults to False.
    """

    name: str = None
    position: int = None
    alias: list[str] = None
    required: bool = False
    regex_lookup_pattern: str = None
    regex_format_pattern: str = None
    remove_para: bool = False
    is_patterned_para = False

    def __init__(self, *, name: str="", alias: list[str]=[], position: int | bool | None=None, required: bool=False, regex_lookup_pattern: str=None, regex_format_pattern: str=None, regex_multiline_mode: bool=False, remove_para: bool=False, is_patterned_para: bool=False) -> None:
        """
        Initializes a TemplateParameter instance with specified attributes.

        Args:
            name (str, optional): The name of the parameter.
            alias (list[str], optional): Aliases for the parameter. Defaults to None.
            position (int, optional): Position in the template. Defaults to None.
            required (bool, optional): Whether the parameter is required. Defaults to False.
            regex_lookup_pattern (str, optional): Regex pattern for lookups. Defaults to None.
            regex_format_pattern (str, optional): Regex pattern for formatting. Defaults to None.
            regex_multiline_mode (bool, optional): Enable multiline regex mode. Defaults to False.
            remove_para (bool, optional): Whether to remove this parameter. Defaults to False.
            is_patterned_para: Defines if it is a para with pattern-like, for lua template usages

            Note:
                - If both position and name/alias are provided, it will return an error
                - If none of name, alias and position is provided, it will return an error
                - If remove_para set to true, then regex_lookup_pattern and regex_format_pattern need to be null, and required need to be false
        """
        self.name = name
        self.alias = alias
        self.position = position
        self.required = required
        self.regex_lookup_pattern = regex_lookup_pattern
        self.regex_format_pattern = regex_format_pattern
        self.regex_multiline_mode = regex_multiline_mode
        self.remove_para = remove_para
        self.is_patterned_para = is_patterned_para

    def test(self, *, is_lua: bool) -> str:
        """
        Validates the current configuration of the TemplateParameter against a given position.

        Checks include:
        - Ensuring either name, alias, or position exists.
        - Verifying that position matches the expected value.
        - Preventing conflicting settings such as both name and position being set.
        - Ensuring required and remove_para are not both True.
        - Checking regex pattern usage does not conflict with remove_para.
        - Validating multiline regex settings.

        Args:
            is_lua: If it is Lua Template

        Returns:
            str: An error message if validation fails; otherwise, an empty string.
        """
        errors: list[str] = []
        if is_str_empty_or_none(self.name) and is_list_empty_or_none(self.alias) and is_int_lt_or_none(x=self.position, target=1):
            errors.append('name, alias and position not exist')

        if not is_str_empty_or_none(self.name) and not is_int_lt_or_none(x=self.position, target=1):
            errors.append('both name and position exist')

        if not is_list_empty_or_none(self.alias) and is_int_lt_or_none(x=self.position, target=1):
            errors.append('both alias and position exist')

        if self.required and self.remove_para:
            errors.append('required and remove_para cannot be True at the same time')

        if (not is_str_empty_or_none(self.regex_lookup_pattern) or not is_str_empty_or_none(self.regex_format_pattern)) and self.remove_para:
            errors.append('regex_lookup_pattern and regex_format_pattern cannot be used with remove_para')

        if not is_str_empty_or_none(self.regex_lookup_pattern) and '\n' in self.regex_lookup_pattern and not self.regex_multiline_mode:
            errors.append('regex_lookup_pattern contains newline characters but regex_multiline_mode is False')

        if not is_lua and self.is_patterned_para:
            errors.append('is_patterned_para cannot set to true if it isn\'t a lua template')

        if len(errors) != 0:
            if not is_str_empty_or_none(self.name):
                raise ValueError(
                    f"TemplateParameter.test() failed, at TemplateParameter.name = {self.name}. The following parameters are not filled: " + ', '.join(str(e) for e in errors))
            elif not is_list_empty_or_none(self.alias):
                raise ValueError(
                    f"TemplateParameter.test() failed,TemplateParameter.alias = {self.alias}. The following parameters are not filled: " + ', '.join(str(e) for e in errors))
        else:
            self._init_for_use()
            return ''

    def _init_for_use(self) -> None:
        if self.name is None:
            self.name = self.alias[0]

        if self.name not in self.alias:
            self.alias.append(self.name)