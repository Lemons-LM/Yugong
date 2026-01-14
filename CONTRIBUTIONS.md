## Code Style and Contribution Guidelines

1. **Use Type Hints Everywhere**  
   All functions, methods, and module-level variables must include [PEP 484](https://peps.python.org/pep-0484/) type annotations. Treat the codebase as if it were statically typed.

2. **Assume Functions Can Fail – Handle Errors Gracefully**  
   Functions used in Extensions must validate their inputs and **avoid** handle errors automatically. Raise clear, descriptive exceptions with meaningful error messages. Avoid silent failures or undefined behavior.

3. **Write Documentation**  
   Provide clear, well-formatted docstrings for:
   - All public functions, classes, and methods intended for use by **extensions**.
   - Any complex or non-obvious internal logic that aids future maintainers.

4. **Design for Simplicity in Extensions**  
   Extension authors may not be expert programmers (some may even use LLMs to generate code). To support them:
   - Make extension development feel like “playing with LEGO” — simple, composable, and predictable.
   - Require extension authors to use `.test()` after they "made a brick"
   - If an extension fails validation or testing, **prevent it from being loaded or executed**, and provide a clear, actionable error message.

5. **Safety Comes First**    
    We don't want to make vandalism to the wiki, even more than to contribute. If something fails the test, make sure the entire program won't execute.

## Jobs
- [ ] Design Tag Arch
- [ ] Fill the code which has doc strs
  - [ ] models
    - [ ] [link_task.py](src/Yugong/models/link_task.py)
    - [x] [marks.py](src/Yugong/models/marks.py)
    - [x] [settings.py](src/Yugong/models/settings.py)
    - [ ] [tag_task.py](src/Yugong/models/tag_task.py)
    - [ ] [template.py](src/Yugong/models/template.py)
    - [ ] [template_parameter.py](src/Yugong/models/template_parameter.py)
    - [x] [wiki.py](src/Yugong/models/wiki.py)
    - [ ] [wikitext](src/Yugong/models/wikitext.py) (Important!)
  - [x] utils
    - [x] [inits.py](src/Yugong/utils/inits.py)
    - [x] [is_empty_or_none.py](src/Yugong/utils/is_empty_or_none.py) Note: Python might not need this
    - [x] [mark_job_intro.py](src/Yugong/utils/mark_job_intro.py)
  - [ ] [yu_gong.py](src/Yugong/yu_gong.py)
- Add doc strs:
  - [ ] [yu_gong.py](src/Yugong/yu_gong.py)
- [ ] Write some Extensions
- [ ] Change [LocalSettings.txt](settings.toml) to TOML and rename as [Settings.toml](Settings.toml), them change LocalSettings/DefaultSettings to just one Settings
- [ ] Write some extensions
- [ ] Write tests
- [ ] Check the todos