import json
import os
import pyperclip
import webbrowser

from src.Yugong.models.logger import logger
from src.Yugong.models.settings import settings
from src.Yugong.models.wiki import wiki_instance
from src.Yugong.models.wikitext import Wikitext
from src.Yugong.utils.mark_job_intro import JOBS

MANIFEST = {}
def do_jobs():
    wiki_instance.init_instance()
    global MANIFEST
    todo_list: list[str] = wiki_instance.get_todo_list()
    
    cache_dir = os.path.join("PROJECT_ROOT", "cache")
    os.makedirs(cache_dir, exist_ok=True)
    
    file_path = os.path.join(cache_dir, f"{settings.wiki_tag}.json")
    
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if wiki_instance.api_endpoint != data["url"]:
                raise ValueError("Instance Url does not match the one in cache. You might need to change the wiki_tag in the settings.toml")
            if "todo" in data:
                todo_list_last = data["todo"]
            else:
                todo_list_last = []
            set_tmp = set(todo_list_last)
            set_tmp.update(todo_list)
            todo_list = list(set_tmp)
            data["todo"] = todo_list
            MANIFEST = data
        with open(file_path, 'w', encoding='utf-8') as f:
            # noinspection PyTypeChecker
            json.dump(data, f, ensure_ascii=False, indent=2)
    else:
        # 创建文件
        with open(file_path, 'w', encoding='utf-8') as f:
            MANIFEST = {"url":wiki_instance.api_endpoint,"todo": todo_list}
            # noinspection PyTypeChecker
            json.dump(MANIFEST,f, ensure_ascii=False, indent=2)

    for page_name in todo_list:
        _process_single_page(page_name)
        MANIFEST["todo"].remove(page_name)
        with open(file_path, 'w', encoding='utf-8') as f:
            # noinspection PyTypeChecker
            json.dump(MANIFEST,f, ensure_ascii=False, indent=2)

    print("All done!")




def _process_single_page(page_name: str):
    metadata: dict[str, str] = wiki_instance.get_metadata(page_name=page_name)
    wikitext: Wikitext = Wikitext(metadata)
    content: str =wiki_instance.get_content(page_name=page_name)
    wikitext.set_content(content)
    step_count: int = 1
    if settings.log_level >= 2:
        logger.log_step(directory=page_name,file_name="000_before_process", content=content)
    if settings.log_level >= 1:
        logger.log_summary(f"\n\nPage name: {page_name}\nEnabled extensions:\n")
    print(f"Begin processing {page_name}:")
    for job in JOBS:
        wikitext_new: Wikitext = job(wikitext)
        if wikitext_new.processed_content != wikitext.processed_content:
            wikitext.update(wikitext_new.processed_content)
            if settings.log_level >= 1:
                logger.log_summary(f'"{job.__name__}", ')
            if settings.log_level >= 3:
                logger.log_step(directory=page_name,file_name=f"{step_count:03d}_after_{job.__name__}", content=wikitext.processed_content)
            step_count += 1

    if settings.log_level >= 2:
        logger.log_step(directory=page_name,file_name="999_after_process", content=wikitext.processed_content)

    if wikitext.processed_content != content:
        if settings.submit_changes:
            wiki_instance.set_content(wikitext)
        else:
            pyperclip.copy(wikitext.processed_content)
            edit_url = f"{wiki_instance.api_endpoint}index.php?title={page_name}&action=edit"
            webbrowser.open(edit_url)
            input("The new wikitext has been copied to your clipboard.\nDue to settings, you need to manually paste and submit it.\nPress any key to continue...")
    else:
        print(f"No changes made to {page_name}, continue.")

