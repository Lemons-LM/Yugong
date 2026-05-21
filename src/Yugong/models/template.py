from src.Yugong.models.marks import Marks
from src.Yugong.models.template_task import TemplateTask


class Template:
    """
    Wiki Template Class
    """
    name: str = None
    position_paras: dict[int, str] = {}
    named_paras: list[dict[str, str]] = []
    id: str = None
    position_must_be_named: bool = False

    def __init__(self) -> None:
        """
        Init it, name and id are required
        """
        return

    def add_pos_para(self, *, position: int, value: str) -> None:
        """
        Add position para
        """
        if not value or not position:
            raise ValueError("position and value cannot be empty")

        self.position_paras[position] = value

    def add_named_para(self, *, name: str, value: str) -> None:
        """
        Add named para
        """
        if not name or not value:
            raise ValueError("name and value cannot be empty")
        self.named_paras.append({"name": name, "value": value})

    # def remove_last_name_para(self) -> None:
    #     """
    #     Remove the last para
    #     """
    #     if self.named_paras:
    #         self.named_paras.pop()

    def to_str(self) -> str:
        """
        Parse the object to a template str, and return it.
        """
        template_str: str = "{{" + self.name
        if self.position_paras:
            # 按照位置键排序字典项
            sorted_items = sorted(self.position_paras.items(), key=lambda item: item[0])
            if self.position_must_be_named:
                for position, value in sorted_items:
                    template_str += "|" + str(position) + '=' + str(value)
            else:
                for position, value in sorted_items:
                    template_str += "|" + str(value)

        if self.named_paras:
            for para in self.named_paras:
                template_str += "|" + str(para["name"]) + '=' + str(para["value"])

        template_str += "}}"
        return template_str

    def parse(self,*, template_dict: dict[str, str], task: TemplateTask) -> None:
        content: str = template_dict['content'][2:-2]



        paras_list: list[str] = content.split('|')
        self.name = paras_list[0].strip()
        self.id  = template_dict['id']
        self.position_must_be_named = task.position_must_be_named
        if not task.position_para:
            for i, para in enumerate(paras_list[1:], 1):
                if '=' in para:
                    name, value = para.split('=', 1)
                    self.add_named_para(name=name.strip(), value=value)
                else:
                    if i > 1:
                        prev_para_name = self.named_paras[-1]['name']
                        prev_para_value = self.named_paras[-1]['value']
                        self.named_paras.pop()
                        new_value = prev_para_value + '{{|}}' + para
                        self.add_named_para(name=prev_para_name, value=new_value)
                    else:
                        self.add_pos_para(value=para)
        else:
            pos: int = 1
            for i, para in enumerate(paras_list):
                if '=' in para:
                    name, value = para.split('=', 1)
                    self.add_named_para(name=name.strip(), value=value)
                else:
                    self.add_pos_para(position=pos, value=para)
                    pos += 1

    def apply(self, task: TemplateTask):
        pass

def find_and_extract_braces(content: str) -> tuple[list[dict[str, str]], str]:
    """
    查找并提取字符串中的花括号内容

    Args:
        content: 要处理的字符串

    Returns:
        tuple: (提取的括号内容列表, 原地替换后的字符串)
    """
    result_str: str = content
    inner_templates: list[dict[str,str]] = []
    template_number: int = 1
    position: int = result_str.find(Marks.lbrace)
    left_position: int = position
    while position != -1:
        brace_count: int = 1
        position += 1
        found_match = False
        while position < len(result_str):
            if result_str[position] == Marks.lbrace:
                brace_count += 1
            elif result_str[position] == Marks.rbrace:
                brace_count -= 1
                if brace_count == 0:
                    # 找到匹配的右括号
                    template_content: str = result_str[left_position:position+1]
                    template_id: str = f'TEMPLATE_{str(template_number)}'
                    tpl: dict[str, str] = {
                        "content": template_content,
                        "id": template_id
                    }
                    template_number += 1
                    inner_templates.append(tpl)
                    result_str = result_str[:left_position] + template_id + result_str[position+1:]
                    found_match = True
                    break
            position += 1
        
        if not found_match:
            # 如果没有找到匹配的括号，则移动到下一个位置继续查找
            position = result_str.find(Marks.lbrace, left_position + 1)
            left_position = position
        else:
            # 继续查找下一个模板
            position = result_str.find(Marks.lbrace, left_position)

    return inner_templates, result_str

if __name__ == "__main__":
    content: str = "Foo|bar={{AAA|BBB}}|c=d|{{{1|}}}|abcd|man!{{man|{{!}}|mannn}}"
    inner_templates, result_str = find_and_extract_braces(content)
    print("result" + result_str)
    print("templates" + str(inner_templates))