from src.Yugong.models.template_parameter import TemplateParameter
from src.Yugong.models.template_task import TemplateTask
from src.Yugong.utils.is_empty_or_none import is_str_empty_or_none, is_list_empty_or_none

#TODO: Change it to link-only
class LinkTask:
    """
    New Link Task, including Link syntax and link syntax.

    The LinkTask.test() should always be run first before action, otherwise, it will throw an error.
    """

    name: str = ''
    have_tested: bool = False
    subtasks: list[TemplateTask] = None