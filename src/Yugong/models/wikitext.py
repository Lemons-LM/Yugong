from src.Yugong.models.marks import Marks
from src.Yugong.models.task import TemplateTask


class Wikitext:
    """
    Wikitext
    """
    title: str = None
    revid: int = None
    text: str = None
    manifest_str: list[str] = None
    manifest_map: list[dict[str, str]] = None
    is_available: bool = False

    def __init__(self, *, title: str, revid: int, text: str) ->  None:
        self.title = title
        self.revid = revid
        self.text = text

    def set_content(self, content: str) -> None:
        if content is not None:
            self.text = content
        else:
            raise ValueError("Content cannot be None")



    def extract_template(self, *, task: TemplateTask) -> None:
        names: list[str] = task.alias
        tmp_str: str = self.text
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
                self.manifest_str.append(template)
                tmp_str = tmp_str[:prev_char_pos] + f'Template_Number_{str(template_number)}' + tmp_str[pos + 1:]
                template_number += 1
                positions.append(pos)
                start = 0
