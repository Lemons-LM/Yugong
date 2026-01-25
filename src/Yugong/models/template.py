class Template:
    """
    Wiki Template Class
    """
    name_str: str = None
    position_paras: dict[int, str] = {}
    named_paras: list[dict[str, str]] = []
    id: str = None
    position_must_be_named: bool = False

    def __init__(self, *, name: str, id: str, position_must_be_named: bool=False) -> None:
        """
        Init it, name and id are required
        """
        if name:self.name_str = name
        if id:self.id = id
        if position_must_be_named: self.position_must_be_named = True

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

    def remove_last_name_para(self) -> None:
        """
        Remove the last para
        """
        if self.named_paras:
            self.named_paras.pop()

    def to_str(self) -> str:
        """
        Parse the object to a template str, and return it.
        """
        template_str: str = "{{" + self.name_str
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