from src.Yugong.models.link_task import LinkTask
from src.Yugong.models.marks import Marks
from src.Yugong.models.settings import settings
from src.Yugong.models.tag_task import TagTask
from src.Yugong.models.template_parameter_task import TemplateParameterTask
from src.Yugong.models.template_task import TemplateTask
from src.Yugong.models.template import Template
import re
from bs4 import BeautifulSoup


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
    tag_obj_list: list[Template] = []
    is_available: bool = False
    item_number: int = 1
    namespace: int = None
    permission: str = None

    def __init__(self, metadata: dict[str,str]) -> None:
        if metadata["title"]:
            self.title = metadata["title"]

        if metadata["revid"]:
            self.revid = int(metadata["revid"])

        if metadata["page_id"]:
            self.page_id = int(metadata["pageid"])

        if metadata["namespace"]:
            self.namespace = int(metadata["namespace"])

        if metadata["permission"]:
            self.permission = metadata["permission"]

    def set_content(self, content: str) -> None:
        if content is not None:
            if not self._original_content:
                self._original_content = content
                self.processed_content = self._original_content
        else:
            raise ValueError("Content cannot be None")

    def update(self, processed_content: str) -> None:
        """
        Update the processed_content from somewhere outside the class
        """
        if processed_content: self.processed_content = processed_content

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

    def to_object(self, *, task: TemplateTask | LinkTask | TagTask) -> None:
        """
        Parsing the str_list to the obj_list.
        If the paras' names could be converted to the preferred ones, convert them this step.
        If para duplicates, follow that the settings instructs
        """
        if isinstance(task, TemplateTask):
            self._template_to_object(task)
        elif isinstance(task, LinkTask):
            self._link_to_object(task)
        else:
            self._tag_to_object(task)

    def apply_task(self, *, task: TemplateTask or LinkTask or TagTask) -> None:
        """
        Apply changes defined in tasks
        """

    def to_str_list(self, *, task: TemplateTask or LinkTask or TagTask) -> None:
        """
        Convert obj_list to str_list
        """

    def to_str(self) -> None:
        """
        Convert the whole object to a string, processed_content
        """

    def check_dangerous(self, *, first_run: bool = False, last_run: bool = False) -> bool:
        """
        check:
        - diff size
        - if there's uncertain tags like font or center
        then follow the LocalSetting/Default

        True to Dangerous,
        False to Safe
        """
        if first_run and last_run:
            raise ValueError("first_run and last_run cannot be both True")
        elif first_run:
            # check if there is some tags not in settings' safe tag list
            result = []

            # 使用BeautifulSoup解析HTML标签
            soup = BeautifulSoup(self.processed_content, 'html.parser')
            all_tags = [tag.name for tag in soup.find_all()]

            if hasattr(settings, 'safe_tag_list'):
                safe_tags = settings.safe_tag_list
            else:
                safe_tags = []
            if hasattr(settings, 'unsafe_tag_list'):
                unsafe_tags = settings.unsafe_tag_list
            else:
                unsafe_tags = []

            if not all_tags:
                return False

            if not safe_tags and unsafe_tags:
                for tag_name in all_tags:
                    if tag_name in unsafe_tags:
                        result.append(tag_name)
            elif not safe_tags and not unsafe_tags:
                for tag_name in all_tags:
                    result.append(tag_name)
            elif safe_tags and not unsafe_tags:
                for tag_name in all_tags:
                    if tag_name not in unsafe_tags:
                        result.append(tag_name)

            if unsafe_tags:
                return True
            else:
                return False

        elif last_run:
            # Compare diff size between _original_content and processed_content
            if self._original_content is not None and self.processed_content is not None:
                diff_size = abs(len(self._original_content) - len(self.processed_content))
                max_diff_size = getattr(settings, 'max_diff_size', 500)
                if diff_size > max_diff_size:
                    return True
                else:
                    return False
        else:
            if self._original_content is not None and self.processed_content is not None:
                diff_size = abs(len(self._original_content) - len(self.processed_content))
                max_diff_size = getattr(settings, 'max_diff_size', 500)
                if diff_size > max_diff_size:
                    return True
                else:
                    return False

    def add_with_condition(self, *, regex: str, condition_tf: bool, add_str: str, before: str, after: str) -> None:
        """
        If condition regex true or false, add sth at where before or after.

        Tips: You might want to add \n before/after the insert
        """

        match_exists = bool(re.search(regex, self.processed_content))

        should_add = (match_exists == condition_tf)

        if should_add:
            if before:
                pattern = f'({re.escape(before)})'
                replacement = f'{add_str}\\1'
                self.processed_content = re.sub(pattern, replacement, self.processed_content)
            elif after:
                pattern = f'({re.escape(after)})'
                replacement = f'\\1{add_str}'
                self.processed_content = re.sub(pattern, replacement, self.processed_content)

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

        if task.namespace != self.namespace:
            return
        if isinstance(task, (TemplateTask, LinkTask)):
            self.extract(task=task)
            if not self.template_str_list and not self.link_str_list:
                return
            self.to_object(task=task)
            self.apply_task(task=task)
            self.to_str_list(task=task)
            self.to_str()
            self.check_dangerous()
        elif isinstance(task, TagTask):
            self.extract(task=task)
            if not self.tag_str_list:
                return
            self.to_object(task=task)
            self.apply_task(task=task)
            self.to_str_list(task=task)
            self.to_str()
            self.check_dangerous()
        else:
            raise ValueError("task must be TemplateTask or LinkTask or TagTask")

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

    def subst_regex(self, *, regex_list: list[str], subst_str: str) -> None:
        """
        subst via regex
        """
        for regex in regex_list:
            self.processed_content = re.sub(regex, subst_str, self.processed_content)

    def _extract_template_or_link(self, *, task: TemplateTask | LinkTask) -> None:
        names: list[str] = task.alias
        tmp_str: str = self.processed_content
        pipe_mark = Marks.pipe

        if isinstance(task, TemplateTask):
            mode = 'template'
            left_mark = Marks.lbrace
            right_mark = Marks.rbrace
        elif isinstance(task, LinkTask):
            mode = 'link'
            left_mark = Marks.lbracket
            right_mark = Marks.rbracket
        else:
            raise ValueError("task must be TemplateTask or LinkTask")
        for name in names:
            start = 0
            while True:
                match = re.search(re.escape(name), tmp_str[start:], re.IGNORECASE)
                if match:
                    pos = start + match.start()
                else:
                    break
                prev_char_pos = pos - 1
                # Check if it is A template but not PART of another template - Part LEFT
                while prev_char_pos >= 0 and tmp_str[prev_char_pos].isspace():
                    prev_char_pos -= 1
                if prev_char_pos < 0 or tmp_str[prev_char_pos] not in [left_mark]:
                    start = pos + 1
                    continue
                if tmp_str[pos] in [left_mark] and tmp_str[pos - 1] in [left_mark] and tmp_str[pos - 2] not in [
                    left_mark]:
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
                template_content = tmp_str[prev_char_pos - 1:pos]
                print(template_content)
                item: dict = {'id': item_tag, 'content': template_content}
                if mode == 'template':
                    self.template_str_list.append(item)
                elif mode == 'link':
                    self.link_str_list.append(item)

                tmp_str = tmp_str[:prev_char_pos - 1] + item_tag + tmp_str[pos + 1:]
                self.processed_content = tmp_str
                self.item_number += 1
                start = 0

    def _extract_tag(self, task: TagTask):
        pass

    def _template_to_object(self, task: TemplateTask):
        """
        Extract the template from str to objs via task
        """
        for t_str in self.template_str_list:
            content = t_str['content'][2:-2]
            paras_list = content.split('|')
            if settings.overwrite_template_name:
                t_obj = Template(name=task.name or task.alias[0], id=t_str['id'], position_must_be_named=task.position_must_be_named)
            else:
                t_obj = Template(name=paras_list[0].strip() or task.alias[0], id=t_str['id'], position_must_be_named=task.position_must_be_named)
            if not task.position_para:
                for i, para in enumerate(paras_list[1:], 1):
                    if '=' in para:
                        name, value = para.split('=', 1)
                        t_obj.add_named_para(name=name.strip(), value=value)
                    else:
                        if i > 1:
                            prev_para_name = t_obj.named_paras[-1]['name']
                            prev_para_value = t_obj.named_paras[-1]['value']
                            t_obj.remove_last_name_para()
                            new_value = prev_para_value + '{{|}}' + para
                            t_obj.add_named_para(name=prev_para_name, value=new_value)
                        else:
                            # 如果是第一个参数且没有等号，作为位置参数处理
                            t_obj.add_pos_para(value=para)
            else:
                pos: int = 1
                for i, para in enumerate(paras_list):
                    if '=' in para:
                        name, value = para.split('=', 1)
                        t_obj.add_named_para(name=name.strip(), value=value)
                    else:
                        t_obj.add_pos_para(position=pos, value=para)
                        pos += 1

            self.template_obj_list.append(t_obj)

    def _link_to_object(self, task: LinkTask):
        pass

    def _tag_to_object(self, task: TagTask):
        pass


if __name__ == '__main__':
    task_normal: TemplateTask = TemplateTask(
        name='Foo',
        alias=['bar', 'test', 'example'],
        parameters=[
            TemplateParameterTask(
                position=1,
                required=True,
                regex_lookup_pattern='^([a-zA-Z0-9]+)$',
                regex_format_pattern='format=$1',
                remove_para=False,
                is_patterned_para=False
            ),
            TemplateParameterTask(
                name='named',
                alias=['npara', 'np'],
                required=False,
                regex_lookup_pattern='^([0-9]+)revoked$',
                regex_format_pattern='format=$1',
                remove_para=False,
                is_patterned_para=False
            ),
            TemplateParameterTask(
                name='removed',
                alias=['rm', 'legacy'],
                required=False,
                remove_para=True,
                is_patterned_para=False
            )
        ],
        no_para_needed=False,
        is_lua_template=False
    )
    task_normal.test()
    task_lua: TemplateTask = TemplateTask(
        name='Lua',
        alias=['l', 'noteta'],
        parameters=[
            TemplateParameterTask(
                position=1,
                required=False,
                regex_lookup_pattern='^([a-zA-Z0-9]+)$',
                regex_format_pattern='format=$1',
                remove_para=False,
                is_patterned_para=True
            ),
            TemplateParameterTask(
                name='T',
                alias=['title'],
                required=False,
                regex_lookup_pattern='^(.*)$',
                regex_format_pattern='format=$1',
                remove_para=False,
                is_patterned_para=False
            ),
            TemplateParameterTask(
                name='G',
                required=False,
                regex_lookup_pattern="G[0-9]+=(.*)",
                regex_format_pattern="G[0-9]+=(.*) True!",
                is_patterned_para=True
            )
        ],
        no_para_needed=False,
        is_lua_template=True
    )
    task_lua.test()
    wikitext: Wikitext = Wikitext({"title": "Wikitext Parser Function Test", "revid": "1", "pageid": "1", "namespace": "0", "permission": ""})
    wikitext.set_content("""
This is the test page of the Wikitext Class Parser Functions. It includes multiple "template tasks" to be fixed properly.
#TODO: Write this.
begin{{foo|a{{{aaa}}}|bc{{BC}}}}end
begin{{Bar|named=123|bc=BC|bar={{Bar}}}}end
begin{{NoteTA
|1=2
|3=4
|2=-{zh-hans: aaa;zh-hant: bbb}-
|T=abcd
|G1=aaaa
|G2=bbbb}}end
    """)
    wikitext.extract(task=task_normal)
    wikitext.extract(task=task_lua)
    print(wikitext.template_str_list)
    print(wikitext.processed_content)