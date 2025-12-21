from src.Yugong.models.template_parameter import TemplateParameter
from src.Yugong.models.template_task import TemplateTask
from src.Yugong.models.wikitext import Wikitext
from src.Yugong.utils.mark_job_intro import job, intro

@job
def template_example_job(wikitext: Wikitext) -> Wikitext:
    """
    If you want to write an Extension, Follow:
    1. Copy the entire page, and paste in the same directory with a different name. Better to follow "template_name.py" format, but don't change the ".py" part, like "template_example"
    2. change "template_example_job" to a name which explains what you are writing about. Better to just be the filename with "_job" without ".py". like "template_example_job".
    3. Define parameters, which is the things before '=' which starts after the line _job: `TemplateTask = TemplateTask(` and before `)` and then `_job.test()`
    4. Clear the words you see here between three ", and write a detailed explanation to what you are writing.
    5. Leave unmentioned part away, and go to lines after @intro, follow intros there

    """
    _job: TemplateTask = TemplateTask(
        name='example',
        alias=['example'],
        parameters=[TemplateParameter(name='test', regex_lookup_pattern=r"(from)(.*?)(regex)", regex_format_pattern=r"$1_$2", alias=['test', 'test2']), TemplateParameter(position=1, remove_para=True)],
        template_type='template'
    )
    _job.test()
    wikitext.do(_job)
    return wikitext

@intro
def template_example_intro() -> str:
    """
    1. Change "template_example_job" to a name which explains what you are writing about. Better to just be the filename with "_intro" without ".py". like "template_example_intro".
    2. Edit the words between ' after "return", make it a very brief introduction to what this extension will do
    3. Save and Exit. Thank you for your work.
    """
    return 'TemplateTask: Formatting template "foo"'