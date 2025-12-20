from src.Yugong.utils.inits import get_settings


def yu_gong():
    """
    1. Welcome the user to use and ask them to confirm knowing they need to take full responsibility to using the program
    2. Do get_settings and ask the user to confirm the program's settings in LocalSettings.txt
    3. Ask the user to confirm the Extensions' job by use all @intro s to print strs that intro each extension's usage
    4. Everything is confirmed, init the wiki_instance and get job list
    5. Do jobs.
    6. (Temporary in MVP) Tell the user result, copy it on the clipboard and then open the browser's action=edit page
    """
    if_know_to_use = input("YuGong is a tool to help you to do some jobs on specific wiki.\n"
                           "It it released \"as-is\", so we won't guarantee it works as expected.\n"
                         "You need to take full responsibility to using the program.\n"
                           "You are solely responsible for ensuring that your use of this software complies with all applicable laws and regulations in your jurisdiction.\n"
                           "Including but not limited to the laws of the People's Republic of China.\n"
                           "Besides that, it is a free software, which means you never need to pay for it.\n"
                         "Do you know that? (y/n): ").lower()
    if if_know_to_use not in ["y", "yes"]:
        print("Goodbye")
        return

    get_settings()