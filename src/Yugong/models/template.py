class Template:
    """
    Wiki Template Class
    """
    name_str: str = None
    position_paras: list[dict[int, str]] = None
    named_paras: list[dict[str, str]] = None
    id: str = None
    para_name: list[str] = None

    def __init__(self, *, name: str, id: str) -> None:
        """
        Init it, name and id are required
        """

    def add_pos_para(self, *, position: int, value: str) -> None:
        """
        Add position para
        """

    def add_named_para(self, *, name: str, value: str) -> None:
        """
        Add named para
        """

    def to_str(self) -> str:
        """
        Parse the object to a template str, and return it.
        """