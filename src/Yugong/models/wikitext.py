from src.Yugong.models.link_task import LinkTask
from src.Yugong.models.marks import Marks
from src.Yugong.models.tag_task import TagTask
from src.Yugong.models.template_task import TemplateTask
from src.Yugong.models.template import Template
from src.Yugong.utils.is_empty_or_none import is_str_empty_or_none


class Wikitext:
    """
    Wikitext
    """
    title: str = None
    revid: int = None
    page_id: int = None
    original_content: str = None
    processed_content: str = None
    template_str_list: list[str] = None
    template_obj_list: list[Template] = None
    link_str_list: list[str] = None
    link_obj_list: list[Template] = None
    tag_str_list: list[str] = None
    tag_obj_list: list[Template] = None
    is_available: bool = False


    def __init__(self, *, title: str, revid: int) ->  None:
        self.title = title
        self.revid = revid

    def set_content(self, content: str) -> None:
        if content is not None:
            self.original_content = content
            if not is_str_empty_or_none(self.original_content):
                self.processed_content = ""
        else:
            raise ValueError("Content cannot be None")

    def extract(self, * task: TemplateTask or LinkTask or TagTask) -> None:
        """
        extracting needed item via different methods/task_type, only to the type's str_list
        """

    def to_object(self, * task: TemplateTask or LinkTask or TagTask) -> None:
        """
        Parsing the str_list to the obj_list.
        If the paras' names could be converted to the preferred ones, convert them this step.
        If para duplicates, follow that the settings instructs
        """

    def apply_task(self, *, task: TemplateTask or LinkTask or TagTask) -> None:
        """
        Apply changes defined in tasks
        """

    def obj_to_str_list(self, *, task: TemplateTask or LinkTask or TagTask) -> None:
        """
        Convert obj_list to str_list
        """

    def to_str(self) -> None:
        """
        Convert the whole object to a string, processed_content
        """

    def check_dangerous(self) -> None:
        """
        check:
        - diff size
        - if there's uncertain tags like font or center
        then follow the LocalSetting/Default
        """

    def add_with_condition(self,* , regex: str, condition_tf: bool, add_str: str, before: str, after:str) -> None:
        """
        If condition regex true or false, add sth at where before or after
        """

    def do(self, *, task: TemplateTask or LinkTask or TagTask) -> None:
        """
        Do different jobs via different data types.
        [check_dangerous] -> [extract] -> [to_object] ->
        [apply_task] -> [obj_to_str_list] -> [to_str] -> [check_dangerous]
        Presenting user a [Wikitext.do(task)] simple something.
        Don't forget to run [task.test()] before running!
        """
        if not task.have_tested:
            task.test()

    def mark_immutable(self) -> None:
        """
        Auto mark immutable items of zh_convert, the Cangjie part. Including:
        - `{{NoteTA}}` Template
        - `-{foo}-` syntax
        - `{{foo}}` templates
        - `{{foo` template start, `|foo=` template para name

        Convert them to something like `[{SUBST_0001}]`
        or something definitely will never be used in all the wikitext syntax
        """

    def subst_regex(self, *, regex_list: list[str]) -> None:
        """
        subst via regex
        """

    def update_processed_content(self, content: str) -> None:
        """
        Update the processed content without clearing all the content.
        This was designed fot something like Cangjie zh-Hans <=> zh-Hant
        We need to make sure extensions cannot use this. Use safer ones instead
        """

    #TODO: This hasn't finished yet
    def _extract_template_or_link(self, *, task: TemplateTask or LinkTask) -> None:
        names: list[str] = task.alias
        tmp_str: str = self.original_content
        positions: list[int] = []
        left_mark = None
        right_mark = None
        pipe_mark = Marks.pipe
        template_number: int = 1

        if task.template_type == 'template':
            left_mark = Marks.lbrace
            right_mark = Marks.rbrace
        elif task.template_type == 'link':
           left_mark = Marks.lbracket
           right_mark = Marks.rbracket

        for name in names:
            start = 0
            while True:
                pos = tmp_str.find(name, start)
                if pos == -1:
                    break
                prev_char_pos = pos - 1
                # Check if it is A template but not PART of another template - Part LEFT
                while prev_char_pos >= 0 and tmp_str[prev_char_pos].isspace():
                    prev_char_pos -= 1
                if prev_char_pos < 0 or tmp_str[prev_char_pos] not in [left_mark]:
                    start = pos + 1
                    continue
                if tmp_str[pos] in [left_mark] and tmp_str[pos - 1] in [left_mark] and tmp_str[pos - 2] not in [left_mark]:
                    prev_char_pos -= 1
                # Check if it is A template but not PART of another template - Part RIGHT
                next_char_pos = pos + len(name)
                while next_char_pos < len(tmp_str) and tmp_str[next_char_pos].isspace():
                    next_char_pos += 1
                if next_char_pos >= len(tmp_str) or tmp_str[next_char_pos] not in [left_mark, pipe_mark]:
                    start = pos + 1
                    continue

                # All checked, find its end.
                mark_num = 2
                while mark_num > 0:
                    pos += 1
                    if tmp_str[pos] in [left_mark]:
                        mark_num += 1
                    elif tmp_str[pos] in [right_mark]:
                        mark_num -= 1

                template = tmp_str[prev_char_pos:pos + 1]
                self.template_str.append(template)
                tmp_str = tmp_str[:prev_char_pos] + f'Template_Number_{str(template_number)}' + tmp_str[pos + 1:]
                template_number += 1
                positions.append(pos)
                start = 0
