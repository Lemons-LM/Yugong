import importlib
from pathlib import Path

from src.Yugong.core.wikitext import Wikitext
from src.Yugong.utilities.mark_job_intro import JOBS
from src.Yugong.utilities.path_helper import PROJECT_ROOT


class Yugong:

    @staticmethod
    def run_dev_mode(input_path: str, output_path: str) -> None:
        """
        Read wikitext from input_path, run all registered @job extensions against it,
        and write the processed result to output_path.

        No wiki connection is needed.
        """
        # Load extensions (same as confirm_settings does)
        steps_path = PROJECT_ROOT / 'src' / 'Yugong' / 'extensions'
        for f in sorted(steps_path.glob("*.py")):
            if f.name == "__init__.py":
                continue
            module_name = f"src.Yugong.extensions.{f.stem}"
            try:
                importlib.import_module(module_name)
            except Exception as e:
                print(f"  Skipping {f.name}: {e}")

        if not JOBS:
            print(f"Warning: No extensions loaded from {steps_path}")

        # Read input
        input_file = Path(input_path)
        if not input_file.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        content = input_file.read_text(encoding='utf-8')
        print(f"Read {len(content)} chars from {input_path}")

        # Minimal metadata for local testing
        metadata = {
            'title': input_file.stem,
            'page_id': '0',
            'pageid': '0',
            'revid': '0',
            'namespace': '0',
            'permission': '',
        }

        wikitext = Wikitext(metadata)
        wikitext.parse(content)

        # Run all jobs
        step = 0
        for job in JOBS:
            old_content = str(wikitext.wikitext)
            job(wikitext)
            new_content = str(wikitext.wikitext)
            wikitext.processed_content = new_content

            if old_content != new_content:
                step += 1
                print(f"  Step {step}: {job.__name__} — changed ({len(new_content)} chars)")

        if step == 0:
            print("No extensions made any changes.")
        else:
            print(f"Total: {step} extension(s) applied changes.")

        # Write output
        output_file = Path(output_path)
        output_file.write_text(str(wikitext.wikitext), encoding='utf-8')
        print(f"Output written to {output_path} ({len(str(wikitext.wikitext))} chars)")

    def do_jobs() -> None:
        # Set api_endpoint from settings and init the pywikibot site
        wiki.api_endpoint = settings.api_endpoint
        _ = wiki.site  # triggers lazy init + OAuth validation

        global MANIFEST
        todo_list: list[str] = _get_todo_list()

        cache_dir = os.path.join(PROJECT_ROOT, "cache")
        os.makedirs(cache_dir, exist_ok=True)

        file_path = os.path.join(cache_dir, f"{settings.wiki_tag}.json")

        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if wiki.api_endpoint != data["url"]:
                    raise ValueError(
                        "Instance Url does not match the one in cache. "
                        "You might need to change the wiki_tag in the settings.toml"
                    )
                todo_list_last = data.get("todo", [])
                todo_set = set(todo_list_last)
                todo_set.update(todo_list)
                todo_list = list(todo_set)
                data["todo"] = todo_list
                MANIFEST = data
            with open(file_path, 'w', encoding='utf-8') as f:
                # noinspection PyTypeChecker
                json.dump(data, f, ensure_ascii=False, indent=2)
        else:
            with open(file_path, 'w', encoding='utf-8') as f:
                MANIFEST = {"url": wiki.api_endpoint, "todo": todo_list}
                # noinspection PyTypeChecker
                json.dump(MANIFEST, f, ensure_ascii=False, indent=2)

        for page_name in todo_list:
            _process_single_page(page_name)
            MANIFEST["todo"].remove(page_name)
            with open(file_path, 'w', encoding='utf-8') as f:
                # noinspection PyTypeChecker
                json.dump(MANIFEST, f, ensure_ascii=False, indent=2)

        print("All done!")

    def _get_todo_list() -> list[str]:
        """Get pages from linked_template and/or category via pywikibot."""
        todo_pages: set[str] = set()

        if hasattr(settings, 'linked_template') and settings.linked_template:
            template_page = pywikibot.Page(
                wiki.site, f"Template:{settings.linked_template}"
            )
            for page in template_page.embeddedin(namespaces=[0]):
                todo_pages.add(page.title())

        if hasattr(settings, 'category') and settings.category:
            cat = pywikibot.Category(
                wiki.site, f"Category:{settings.category}"
            )
            for page in cat.members(namespaces=[0]):
                todo_pages.add(page.title())

        if not todo_pages:
            raise ValueError("No linked_template or category specified in settings")

        return list(todo_pages)

    def _process_single_page(page_name: str) -> None:
        pwb_page = wiki.page(page_name)
        metadata: dict[str, str] = {
            'title': pwb_page.title(),
            'pageid': str(pwb_page.pageid),
            'revid': str(pwb_page.latest_revision_id),
            'namespace': str(pwb_page.namespace()),
            'permission': '',
        }

        wikitext: Wikitext = Wikitext(metadata)
        content: str = pwb_page.text
        wikitext.parse(content)

        step_count: int = 1
        logger.debug(f"[{page_name}] 000_before_process: {len(content)} chars")
        logger.info(f"Page: {page_name}")
        print(f"Begin processing {page_name}:")

        for job in JOBS:
            old_content = str(wikitext.wikitext)
            job(wikitext)
            new_content = str(wikitext.wikitext)
            wikitext.processed_content = new_content

            if old_content != new_content:
                logger.info(f"Extension applied: {job.__name__}")
                logger.debug(
                    f"[{page_name}] step {step_count:03d} after {job.__name__}: "
                    f"{len(new_content)} chars"
                )
                step_count += 1

        logger.debug(
            f"[{page_name}] 999_after_process: {len(str(wikitext.wikitext))} chars"
        )

        if content != str(wikitext.wikitext):
            if settings.submit_changes:
                # ── Auto/robot mode: save directly, no human interaction ──
                try:
                    pwb_page.text = wikitext.processed_content
                    pwb_page.save(summary=settings.edit_comment, bot=True)
                    print(f"Successfully submitted changes to {page_name}")
                except Exception as e:
                    logger.error(f"Failed to submit {page_name}: {e}")
            else:
                # ── Manual mode: clipboard + browser + user pastes ──────
                pyperclip.copy(str(wikitext.wikitext))
                edit_url = (
                    f"{wiki.api_endpoint}index.php"
                    f"?title={page_name}&action=edit"
                )
                webbrowser.open(edit_url)
                input(
                    "The new wikitext has been copied to your clipboard.\n"
                    "Due to settings, you need to manually paste and submit it.\n"
                    "Press any key to continue..."
                )
        else:
            print(f"No changes made to {page_name}, continue.")

