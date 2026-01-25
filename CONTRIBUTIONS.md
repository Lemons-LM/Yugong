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
    - [x] [logger.py](src/Yugong/models/logger.py)
    - [x] [marks.py](src/Yugong/models/marks.py)
    - [x] [settings.py](src/Yugong/models/settings.py)
    - [ ] [tag_task.py](src/Yugong/models/tag_task.py)
    - [x] [template.py](src/Yugong/models/template.py)
    - [ ] [template_parameter.py](src/Yugong/models/template_parameter_task.py)
    - [x] [wiki.py](src/Yugong/models/wiki.py)
    - [ ] [wikitext](src/Yugong/models/wikitext.py) (Important!)
  - [x] utils
    - [x] [confirm_settings.py](src/Yugong/utils/confirm_settings.py)
    - [x] [do_jobs.py](src/Yugong/utils/do_jobs.py)
    - [x] [mark_job_intro.py](src/Yugong/utils/mark_job_intro.py)
    - [x] [path_helper.py](src/Yugong/utils/path_helper.py)
  - [x] [yu_gong.py](src/Yugong/yu_gong.py)
- [ ] Check logic:
  - [ ] We currently removed a function which ignores what python's comparing logic is. So we might need to check if any logic is wrong.
- [ ] Write some extensions
- [ ] Write tests
- [ ] Check the todos