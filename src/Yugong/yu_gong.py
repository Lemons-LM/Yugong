from src.Yugong.utils.confirm_settings import confirm_settings
from src.Yugong.utils.do_jobs import do_jobs


def yu_gong():
    """
    [done] 1. Welcome the user to use and ask them to confirm knowing they need to take full responsibility to using the program
    [done]2. Do get_settings and ask the user to confirm the program's settings in settings.toml
    [done]3. Ask the user to confirm the Extensions' job by use all @intro s to print strs that intro each extension's usage
    [done]4. Everything is confirmed, init the wiki_instance and get job list
    5. Do jobs.
    6. (Temporary in MVP) Tell the user result, copy it on the clipboard and then open the browser's action=edit page
    """
    confirm_settings()
    do_jobs()

