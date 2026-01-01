class LocalSettings:
    """
    When do [get_settings], set needed names defined in /LocalSettings.txt
    Using someway to make it could be used, by using [LocalSettings.foo]
    if there is something LocalSettings have, overwrite them defined in DefaultSettings.
    Don't forget to do with the comments in the file!
    If the consumer is owner_only, load [access_token] from System Environments, in the [WikiInstance]
    """
    @classmethod
    def add(cls, *, key: str, value: str):
        setattr(cls, key, value)



class DefaultSettings:
    """
    Default settings for the script.
    """
    user_agent: str = "Yugong/1.0(Gecko-like, Repository/github.com:Lemons-LM/Yugong), Python/3.12"
    request_max_tries: int = 3
    edit_comment: str = "Edited by Yugong (gh:Lemons-LM/Yugong) program"
    is_dangerous_tag_unacceptable: bool = True
    safe_tag_list: list[str] = [
        'ref'
    ]
    max_acceptable_diff_size: str = 1000
    enable_cangjie: bool = False



local_settings: LocalSettings = LocalSettings()
default_settings: DefaultSettings = DefaultSettings()