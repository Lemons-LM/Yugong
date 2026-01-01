from typing import Final

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
    _original_content: str = None
    processed_content: str = None
    template_str_list: list[dict] = []
    template_obj_list: list[Template] = []
    link_str_list: list[dict] = []
    link_obj_list: list[Template] = []
    tag_str_list: list[dict] = []
    tag_obj_list: list[Template] =[]
    is_available: bool = False
    item_number: int = 1



    def __init__(self, *, title: str, revid: int) ->  None:
        if title: self.title = title
        if revid: self.revid = revid

    def set_content(self, content: str) -> None:
        if content is not None:
            if is_str_empty_or_none(self._original_content):
                self._original_content = content
                self.processed_content = self._original_content
        else:
            raise ValueError("Content cannot be None")

    def extract(self, *, task: TemplateTask | LinkTask | TagTask) -> None:
        """
        extracting needed item via different methods/task_type, only to the type's str_list
        """
        if isinstance(task, (TemplateTask, LinkTask)):
            self._extract_template_or_link(task=task)
        elif isinstance(task, TagTask):
            self._extract_tag(task=task)
        else:
            raise ValueError("task must be TemplateTask or LinkTask or TagTask")

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

    def check_dangerous(self, *, first_run: bool=False, last_run: bool=False) -> None:
        """
        check:
        - diff size
        - if there's uncertain tags like font or center
        then follow the LocalSetting/Default
        """
        if first_run and last_run:
            raise ValueError("first_run and last_run cannot be both True")
        elif first_run:
            # check if there is some tags not in settings' safe tag list
        elif last_run:
            # Compare diff size between _original_content and processed_content
        else:
            self.check_dangerous()

    def add_with_condition(self,* , regex: str, condition_tf: bool, add_str: str, before: str, after:str) -> None:
        """
        If condition regex true or false, add sth at where before or after
        """

    def do(self, task: TemplateTask or LinkTask or TagTask) -> None:
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
        - `{{foo}}` templates [to be discussed]
        - `{{foo` template start, `|foo=` template para name
        - `File:`/`Image:` every parameter start with these namespaces
        - `[[]]` in-wiki link
        - `gallery` tag or templates

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

    def _extract_template_or_link(self, *, task: TemplateTask | LinkTask, from_place: str=None, to_place=None) -> None:
        names: list[str] = task.alias
        tmp_str: str = self.processed_content
        left_mark: str = ""
        right_mark: str = ""
        pipe_mark = Marks.pipe
        mode: str= ''

        if isinstance(task, TemplateTask):
            mode = 'template'
        elif isinstance(task, LinkTask):
            mode = 'link'
        else:
            raise ValueError("task must be TemplateTask or LinkTask")

        if mode == 'template':
            left_mark = Marks.lbrace
            right_mark = Marks.rbrace
        elif mode == 'link':
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

                item_tag: str = f'Item_Number_{str(self.item_number)}'
                item: dict = {'name': item_tag, 'content': tmp_str[pos:next_char_pos + 1]}
                if mode == 'template':
                    self.template_str_list.append(item)
                elif mode == 'link':
                    self.link_str_list.append(item)

                tmp_str = tmp_str[:prev_char_pos] + item_tag + tmp_str[pos + 1:]
                self.item_number += 1
                start = 0

    def _extract_tag(self, task: TagTask):
        pass
