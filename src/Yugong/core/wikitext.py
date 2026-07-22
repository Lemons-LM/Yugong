import mwparserfromhell as mph

#TODO: Unfinished
class Wikitext:
    """
    Wikitext
    """
    title: str = None
    revid: int = None
    page_id: int = None
    _original_content: str = None
    processed_content: str = None
    namespace: int = None
    permission: str = None
    wikitext: mph.wikicode.Wikicode = None

    def __init__(self, metadata: dict[str, str]) -> None:
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

    def __str__(self):
        return str(self.wikitext)

    def parse(self, content: str) -> None:
        """
        Parse the content to Wikicode Object
        """
        self._original_content = content
        self.processed_content = content
        self.wikitext = mph.parse(content)

    def update(self, content) -> None:
        """
        Set the content to Wikicode Object
        """
        if type(content) == str:
            self.processed_content = content
            self.wikitext = mph.parse(content)
        elif type(content) == mph.wikicode.Wikicode:
            self.processed_content = str(content)
            self.wikitext = content
        else:
            raise TypeError("Content must be str or Wikicode")

