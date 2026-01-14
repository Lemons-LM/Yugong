class Settings:
    """
    Default settings for the script.
    """
    user_agent: str = "Yugong/1.0(Gecko-like, Repository/github.com:Lemons-LM/Yugong), Python/3.12"
    request_max_tries: int = 3
    edit_comment: str = "Edited by Yugong (gh:Lemons-LM/Yugong) program"

    is_dangerous_tag_unacceptable: bool = True
    safe_tag_list: list[str] = [
        'ref',
        'br',
        'references'
    ]
    max_acceptable_diff_size: str = 1000
    enable_cangjie: bool = False
    @classmethod
    def set(cls, *, key: str, value: str):
        setattr(cls, key, value)



settings: Settings = Settings()