class WikiInstance:
    api_endpoint: str = None
    user_agent: str = None
    is_owner_only: bool = False
    client_id: str = None
    # Above are changeable, below are unchangeable outside
    action_endpoint: str = None
    rest_endpoint: str = None
    access_token: str = None
    refresh_token: str = None
    permissions: list[str] = None

    def __init__(self):
        return

    def update_settings(self, *, api_endpoint: str = None, user_agent: str = None, client_id: str = None) -> None:
        """
        update settings which could be updated outside the object. Generate action/rest endpoint
        """

    def authorise(self) -> None:
        """
        Authorize via OAuth2, or get [access_token] from the system environment
        If [access_token] expires, get a new one.
        Get bot permissions at the same time
        """

    def get_todo_list(self) -> list[str]:
        """
        Get To-Do list via LocalSettings, and Action API Endpoint.
        Return as a list of page names
        """

    def get_metadata(self, *, pageid: int=None, page_name: str=None) -> dict[str, str]:
        """
        Get specific page metadata via Action API Endpoint.
        Including:
        - pageid
        - revid
        - name
        - namespace
        - permission
        with NO:
        - content (wikitext)
        and return in a map.
        """

    def get_content(self, page_name: str) -> str:
        """
        Get Wikitext via page_name and REST API Endpoint
        """

    def set_content(self, page_name: str) -> None:
        """
        Set Wikitext via page_name and REST API Endpoint
        """