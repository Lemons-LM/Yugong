from src.Yugong.models.template_task import TemplateTask

#TODO: Change it to link-only
class LinkTask:
    """
    New Link Task, including Link syntax and link syntax.

    The LinkTask.test() should always be run first before action, otherwise, it will throw an error.
    """

    name: str = ''
    have_tested: bool = False
    subtasks: list[TemplateTask] = None
    namespace: int = 0