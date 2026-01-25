from src.Yugong.models.template_parameter_task import TemplateParameterTask
class TemplateTask:
    """
    New Template Task, including template syntax and link syntax.

    The TemplateTask.test() should always be run first before action, otherwise, it will throw an error.
    """

    name: str = ''
    have_tested: bool = False
    alias: list[str] = None
    parameters: list[TemplateParameterTask] = None
    named_para: list[TemplateParameterTask] = None
    position_para: list[TemplateParameterTask] = None
    rename_para: bool = False
    no_para_needed: bool = False
    is_lua_template: bool = False
    position_must_be_named: bool = False # force |1=foo|2=bar
    namespace = 0

    def __init__(self, *, name: str, alias: list[str]=None, parameters: list[TemplateParameterTask], rename_para: bool=False,
                 no_para_needed: bool=False, is_lua_template: bool=False) -> None:
        """
        Initialize a TemplateTask instance.

        Args:
            name (str, REQUIRED): The name of the task.
            alias (list[str]): Alternative names (redirects) for the task.
            parameters (list[TemplateParameterTask]): Required parameters for the task.
            rename_para (bool, default to False): Whether parameters should be auto renamed to the 'name' attr.
            template_type (str, REQUIRED): Type of the template ('template', refers to '{{}}' syntax or 'link', refers to '[[]]' syntax). Default to template
            no_para_needed (bool, default to False): Whether the task requires any parameters.
        """
        self.name = name
        self.alias = alias
        self.parameters = parameters
        self.no_para_needed = no_para_needed
        self.rename_para = rename_para
        self.is_lua_template = is_lua_template

    def test(self) -> None:
        """
        Whatever the task is, if TemplateTask.test() has not run first, it will throw an Error.
        Test aimed to make sure all the needed paras are filled, and all the types are at the right data type.
        """
        if self.have_tested:
            return
        failed_list: list[str] = []
        if not self.name and not self.alias:
            failed_list.append('name')

        if not self.no_para_needed and not self.parameters:
            failed_list.append('parameters')

        for para in self.parameters:
            test_result: str= para.test(is_lua=self.is_lua_template)
            if  test_result:
                failed_list.append(str(self.parameters.index(para)))

        if len(failed_list) != 0:
            if  self.name:
                raise ValueError(
                    f"TemplateTask.test() failed, at TemplateTask.name = {self.name} the following parameters are not filled:\n\n" + '\n'.join(str(e) for e in failed_list))
            elif  self.alias:
                raise ValueError(
                    f"TemplateTask.test() failed,TemplateTask.alias = {self.alias}, the following parameters are not filled:\n\n" + '\n'.join(str(e) for e in failed_list))
            else:
                raise ValueError(
                    f"TemplateTask.test() failed, with no name or alias, the following parameters are not filled:\n\n" + '\n'.join(str(e) for e in failed_list))
        else:
            self._init_for_use()
            self.have_tested = True

    def _init_for_use(self) -> None:
        if self.name is None:
            self.name = self.alias[0]

        if self.name not in self.alias:
            self.alias.append(self.name)

        for para in self.parameters:
            if para.position:
                self.position_para.append(para)
            else:
                self.named_para.append(para)