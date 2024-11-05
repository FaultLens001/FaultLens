from copy import deepcopy
from docstring_parser import parse
from src.codebase import CodeBase
from src.record import log_exception
from src.tools.utils import process_method_input


def get_tools_list():
    fl_agent_tools = [
        "extract_method",
        "get_class_info",
        "get_covered_files_from_dir",
        "get_inner_class_info",
        "get_imports"
    ]
    return fl_agent_tools


class ToolsInvoker:

    def __init__(self, codebase: CodeBase):
        self.codebase = codebase

    @classmethod
    def generate_tool_calls_data(cls, tools):

        # template from https://platform.openai.com/docs/assistants/tools/function-calling
        tool_template = {
            "type": "function",
            "function": {
                "name": "",
                "description": "",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        }

        tool_data = []
        for tool_name in tools:
            tool_obj = deepcopy(tool_template)
            tool_obj["function"]["name"] = tool_name
            func_obj = getattr(cls, tool_name)
            # Extract the docstring of each tool
            tool_doc = parse(func_obj.__doc__)
            description = (tool_doc.short_description or "") + "\n" + (tool_doc.long_description or "")
            tool_obj["function"]["description"] = description
            doc_params = tool_doc.params
            for doc_param in doc_params:
                param_name = doc_param.arg_name
                param_type = doc_param.type_name
                desc = doc_param.description
                is_optional = doc_param.is_optional
                tool_obj["function"]["parameters"]["properties"][param_name] = {
                    "type": param_type,
                    "description": desc,
                }
                if not is_optional:
                    tool_obj["function"]["parameters"]["required"].append(param_name)
            tool_data.append(tool_obj)
        return tool_data

    def extract_tool_calls(self, tool_calls):

        calls_record = []
        error_info_list = []  # Tool name does not match, or there is an issue with the parameters
        func_res_list = []  # Tool Outputs
        for tool_call in tool_calls:
            self.codebase.extract_classes_info.clear()
            self.codebase.extract_methods_info.clear()

            tool_id = tool_call.get("func_id")
            tool_name = tool_call.get("func_name")
            tools_list = get_tools_list()

            if tool_name not in tools_list:
                error_info_list.append(
                    {"content": f"Tool {tool_name} is not supported in our tool list.", "func_id": tool_id})
                continue
            func_call = getattr(self, tool_name)

            try:
                func_dict = {"func_name": tool_name, "args_dict": tool_call.get("args_dict")}
                calls_record.append(func_dict)
                res = func_call(**tool_call.get("args_dict"))
                func_res_list.append({"func_id": tool_id, "content": res})
            except Exception as e:
                # The agent may have confused the number or names of the input parameters.
                log_exception(e)
                error = str(e)

                if "got an unexpected keyword argument" in error:
                    error += ". Please check the parameter names or consider switching to a more suitable tool."
                error_info_list.append(
                    {"content": f"Tool {tool_name} returned error message:{error}", "func_id": tool_id})

        return func_res_list, error_info_list, calls_record

    # ====================== tools ======================#

    def get_inner_class_info(self, class_name: str, inner_class_name: str, file_path="") -> str:
        """ Get inner class information.

        Returns the content of the inner class (including all the fields and covered methods).

        Args:
            class_name (string): Name of the outer class.
            inner_class_name (string): Name of the inner class.

        Returns:
            the inner class information or error message.
        """
        return self.codebase.get_inner_class_info(class_name, inner_class_name, file_path=file_path)

    def get_class_info(self, class_name: str, file_path=""):
        """Get class information from a given file or the codebase.

        Returns the class information (package, inherits, implements, comment (javadoc), fields list, covered methods list...) If any covered inner classes or inner interfaces exist, their names will also be provided.


        Args:
            class_name (string): Name of the class to be extracted. This parameter must be provided and cannot be an empty string.
            file_path (string): If provided, the extraction will prioritize class in this file. Can be an empty string if unknown.

        Returns:
            The searched class information or error message.
        """

        return self.codebase.get_class_info(class_name=class_name, raw_file_path=file_path)

    def extract_method(self, method_name: str, class_name="", file_path="", extract_location=False):
        """ Extract a method from a given class or file, with coverage information.

        This function returns the actual code of the method. If the method has lines that were covered during test execution, those lines will be marked with the comment `//**covered**` at the end of each covered line.


        Args:
            method_name (string): Name or signature of the method to be extracted. This parameter must be provided and cannot be an empty string.
            class_name (string): If provided, the extraction will prioritize methods in this class. Can be an empty string if unknown.
            file_path (string): If class_name is not provided, this file will be considered for method extraction. Can be an empty string if unknown.

        Note:
            If both class_name and file_path are provided, the method extraction will prioritize using class_name.

        Returns:
            The extracted method code, annotated with coverage information where applicable, or an error message if the method was not covered during test execution.
        """

        preprocess = process_method_input(method_name)
        if not preprocess:
            return "The method name is invalid.\n"
        msg, candidate_list = self.codebase.extract_method(original_method=method_name, method=preprocess,
                                                           class_name=class_name, file=file_path)
        if extract_location:
            return msg, candidate_list
        else:
            return msg

    def extract_method_from_class(self, method_name: str, class_name: str, extract_location=False):
        """ Extract a method from a given class.

        Returns the actual code of the method.

        Args:
            method_name (string): Name or signature of the method to be extracted. This parameter accepts both the simple method name or its full signature for precise identification.
            class_name (string): Consider only methods in this class.

        Returns:
            the extracted method or error message.
        """
        preprocess = process_method_input(method_name)

        if not preprocess:
            msg = "The method name is invalid.\n"
            if extract_location:
                return msg, None
            else:
                return msg

        msg, candidate_list = self.codebase.extract_method_from_class(preprocess, class_name,
                                                                      extract_location=extract_location)
        if extract_location:
            return msg, candidate_list
        else:
            return msg

    def get_covered_files_from_dir(self, dir_path: str) -> str:
        """Get the list of files in the directory that were covered during test execution.

         This function returns the names of files that have coverage information from
        the test case execution.

        Args:
                dir_path (string): Relative path of the directory.

        Returns:
             the list of Java file names that were covered or an error message if none were found.
        """
        return self.codebase.get_files_from_dir(dir_path)

    def get_imports(self, file_path: str) -> str:
        """Retrieve a list of libraries imported in the specified file.

        Args:
            file_path (string): Path of the file.

        Returns:
            List of imported libraries.
        """
        return self.codebase.get_imports(file_path)




