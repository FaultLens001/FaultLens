from tree_sitter import Language, Parser
import json
import os

from src.dataset.repo_d4j import recognize_pattern
from src.tools.auxiliary import find_target_and_comments, extract_children_from_class, extract_inheritance_info, \
    extract_imports, extract_innerclass_from_class, \
    extract_info_from_innerclass, extract_signature_changed, find_method_node
from typing import List, Dict
import re
from config.constants import TREE_SITTER_JAVA_LIB, covered_info_d4j_1_2
from src.tools.auxiliary_tools import _get_package_name, _get_imports
import chardet

JAVA_LANGUAGE = Language(TREE_SITTER_JAVA_LIB, 'java')
method_upper_bound = 50
files_from_dir_upper_bound = 30


def clean_comment(comment):
    javadoc_pattern = re.compile(r'/\*\*.*?\*/', re.DOTALL)
    javadocs = javadoc_pattern.findall(comment)
    javadocs_combined = "\n".join(javadocs)
    return javadocs_combined


def get_file_name(class_name, codebase_path, type):
    proj_main_pattern, proj_test_pattern = recognize_pattern(codebase_path)
    if (not proj_main_pattern) or (not proj_test_pattern):
        # print_and_log("Failed to recognize the source and test folders.\n")
        return ""

    if type == "main":
        dir_prefix = proj_main_pattern
    else:
        dir_prefix = proj_test_pattern

    if dir_prefix:
        rel_path = class_name.replace(".", "/")
        return os.path.join(dir_prefix, rel_path)
    else:
        # print_and_log(f"cannot find prefix!")
        return ""


def read_lines_from_file_with_cov(file_path, start_line, end_line, covered_lines):
    content = []

    encoding = detect_file_encoding(file_path)
    with open(file_path, 'r', encoding=encoding) as file:

        for current_line_number, line in enumerate(file, start=1):
            if int(start_line) <= current_line_number <= int(end_line):
                if current_line_number in covered_lines:
                    line = line.rstrip() + "  //**covered**\n"
                content.append(line)
            elif current_line_number > int(end_line):
                break
    return ''.join(content)


class CodeBase:
    """support information extraction for code exploration tools"""

    def __init__(self, codebase_path, parse_files_path):
        # source code path
        self.codebase_path = codebase_path
        self.parse_files_path = parse_files_path
        self.file_classes_list: Dict[str, List[str]] = {}
        self.classes_list: List[str] = []
        self.java_file_relpaths: List[str] = []
        self.extract_methods_info: List[Dict] = []
        self.extract_classes_info: List[Dict] = []
        self.possible_paths_list: List[str] = []
        # for self-check
        self.extracted_methods_list = []
        self.covered_line_src = {}
        self.covered_line_test = {}

    def clean_info(self, file, info):
        cleaned_info = []
        for element in info:
            start_line = element["start_line"]
            end_line = element["end_line"]
            number_list = self.get_covered_lines(file, start_line, end_line)
            if number_list:
                cleaned_info.append(element)

        return cleaned_info

    def read_covered_info(self, project, bug_id, trigger_test):
        target_covered_info = os.path.join(covered_info_d4j_1_2, project + "_" + str(bug_id))
        src_cov_path = os.path.join(target_covered_info, "src_cov", trigger_test)
        test_cov_path = os.path.join(target_covered_info, "test_cov", trigger_test)
        with open(src_cov_path, "r") as f:
            src_cov = json.load(f)
        with open(test_cov_path, "r") as f:
            test_cov = json.load(f)
        for element in src_cov:
            class_name = element["class_name"].strip()
            file_name = get_file_name(class_name, self.codebase_path, type="main")
            file_name = file_name.strip()
            file_name += ".java"
            if not file_name:
                continue
            line_number = element["line_number"]
            if file_name not in self.covered_line_src:
                self.covered_line_src[file_name] = [int(line_number)]
            else:
                self.covered_line_src[file_name].append(int(line_number))
        for element in test_cov:
            class_name = element["class_name"].strip()
            file_name = get_file_name(class_name, self.codebase_path, type="test")
            file_name = file_name.strip()
            file_name += ".java"
            if not file_name:
                continue
            line_number = element["line_number"]
            if file_name not in self.covered_line_test:
                self.covered_line_test[file_name] = [int(line_number)]
            else:
                self.covered_line_test[file_name].append(int(line_number))

    def get_extracted_methods_list(self):
        return self.extracted_methods_list

    def load_parsed_files(self, summary_json):
        with open(summary_json, 'r') as f:
            data = json.load(f)
            self.java_file_relpaths = data.keys()
            self.file_classes_list = data

        # extract classes from file_classes_list
        for class_list in self.file_classes_list.values():
            for c in class_list:
                self.classes_list.append(c)


    def construct_method_message(self, method_signature, extract_methods_info=None, jump_mode=False,
                                 extract_location=False, jump_index=0, append_to_extracted=False):

        """Construct the message of the extracted method(s)"""
        msg = ""
        local_methods_info = extract_methods_info if extract_methods_info else self.extract_methods_info
        signature_candidate_count = 0
        normal_candidate_count = len(local_methods_info)
        candidates = []
        signature_candidates = []
        for index, item in enumerate(local_methods_info):
            if item["signature"] == method_signature:
                signature_candidate_count += 1
                signature_candidates.append(item)

        if signature_candidates:
            candidates = signature_candidates
        else:
            candidates = local_methods_info


        no_covered_count = 0
        covered_candidates = []
        covered_index = 0
        for item in candidates:
            target_file = os.path.join(self.codebase_path, item["file"])
            start_line = item["start_line"]
            end_line = item["end_line"]
            signature = item["signature"]
            comment = item["comment"]
            javadoc_comment = clean_comment(comment)
            parent_type = item.get("parent_type")
            parent_name = item.get("parent_name")
            # method_content = read_lines_from_file(target_file, start_line, end_line)
            covered_lines = self.get_covered_lines(item["file"], start_line, end_line)

            if not covered_lines:
                no_covered_count += 1
                continue

            covered_index += 1
            if jump_mode:
                if len(candidates) > 1:
                    msg += f'\nMethod Definition {covered_index}:\n'
            else:
                msg += f'\n({covered_index})'

            covered_candidates.append(item)
            method_content = read_lines_from_file_with_cov(target_file, start_line, end_line, covered_lines)


            if (not extract_location) and append_to_extracted:
                # print(f"extracted_methods_list append method")
                self.extracted_methods_list.append(
                    {"file": item["file"], "start_line": start_line, "end_line": end_line})


            item["code"] = method_content

            msg += f'<file>{item["file"]}</file>'
            if parent_type and parent_name:
                msg += f' <{parent_type}>{parent_name}</{parent_type}> '

            msg += f'<method_signature>{signature}</method_signature>\n'
            # if not code_blocked:
            if comment:
                msg += f'<comment>\n{javadoc_comment}\n</comment>\n<code>\n{method_content}</code>\n'

            else:
                msg += f'<code>\n{method_content}\n</code>\n'

        return msg, covered_candidates

    def find_possible_paths(self, file_path):
        self.possible_paths_list.clear()

        for relpath in self.java_file_relpaths:
            file_path_normalized = os.path.normpath(file_path)
            relpath_normalized = os.path.normpath(relpath)

            file_path_parts = file_path_normalized.split(os.sep)
            relpath_parts = relpath_normalized.split(os.sep)

            if relpath_parts[-len(file_path_parts):] == file_path_parts:
                self.possible_paths_list.append(relpath)

    def get_class_info(self, class_name: str, raw_file_path: str):
        """Implementation of the tool `get_class_info`"""

        # If the path is not empty, use get_class_info_from_file
        message = f'Result of get_class_info(class_name="{class_name}",file_path="{raw_file_path}"):\n'
        if raw_file_path != "" and ("..." not in raw_file_path):

            msg = self.get_class_info_from_file(class_name, raw_file_path)
            msg = msg.lstrip()
            if msg.startswith("Cannot find"):
                msg_from_codebase = self.get_class_info_from_codebase(class_name)
                if msg_from_codebase.startswith("Cannot find class"):
                    return message + msg
                else:
                    message += msg
                    message += "However, we find the class in the codebase:\n"
                    message += msg_from_codebase
                    # print_and_log("get_class_info:provide file_path but can only find class in codebase.")
                    return message
            else:
                return message + msg

        # If not found, fallback to get_class_from_codebase to search again
        else:
            msg = self.get_class_info_from_codebase(class_name)
            return message + msg

    def extract_method(self, original_method: str, method: Dict, class_name: str, file: str):
        """Implementation of the tool `extract_method`"""

        message = f'Result of extract_method(method_name="{original_method}",class_name="{class_name}",file_path="{file}"):\n'

        if class_name != "":

            msg, candidate_list = self.extract_method_from_class(method, class_name)

            if candidate_list:
                if file != "":
                    filtered_list = []
                    need_reconsctruct = False
                    for item in candidate_list:
                        if item["file"] != file:
                            need_reconsctruct = True
                            self.remove_extracted_method(item)
                        if item["file"] == file:
                            filtered_list.append(item)
                    if filtered_list:
                        if need_reconsctruct:
                            # print_and_log("extract_method: need to reconstruct message")
                            message += self.reconstruct_method_message(filtered_list)

                        else:
                            message += msg
                        return message, filtered_list

                    # The candidate_list is empty after filtering, indicating that the extracted method's file does
                    # not fully match the one specified by the agent. We need to provide a notification.

                    else:
                        message += "Successfully extracted the method from the specified class, but the file path does not completely match the specified file path.\n" + msg

                else:
                    # print_and_log("extract_method: class_name is not empty, but file is empty")
                    message += msg

                return message, candidate_list

        # The class is empty, or the class does not contain the method
        # fallback to extract_method_from_file to search again
        if file != "":
            # print_and_log("extract_method: class_name is empty or not found, but file is not empty")
            msg, candidate_list = self.extract_method_from_file(method, file)
            if candidate_list:
                if class_name != "":
                    message += "Cannot find the method in the specified class, but successfully extracted the method from the specified file.\n" + msg
                else:
                    message += msg
                return message, candidate_list

        # fallback to extract_method_from_codebase to search again
        msg, candidate_list = self.extract_method_from_codebase(method)
        if candidate_list:
            if (class_name != "") and (file != ""):
                message += "Cannot find the method in the specified class and file, but successfully extracted the method from the codebase.\n" + msg

            elif class_name != "":
                message += "Cannot find the method in the specified class, but successfully extracted the method from the codebase.\n" + msg

            elif file != "":
                message += "Cannot find the method in the specified file, but successfully extracted the method from the codebase.\n" + msg
            return message, candidate_list

        # The method could not be found as a covered one.
        else:
            if (class_name != "") and (file != ""):
                message += "The specified method in the class and file was not covered during test execution.\n"
            elif class_name != "":
                message += "The specified method in the class was not covered during test execution.\n"
            elif file != "":
                message += "The specified method in the file was not covered during test execution.\n"
            else:
                message += "The specified method was not covered during test execution\n"
            return message, candidate_list


    def extract_method_from_class(self, method: Dict, class_name: str, extract_location=False):
        method_name = method.get("name")
        class_name = class_name.strip()
        if ("." in class_name) or ("$" in class_name):
            class_name = class_name.split(".")[-1]
            class_name = class_name.split("$")[-1]
            # print_and_log("extract_method_from_class meet . or $ !")
        resflag, message = self._extract_method_from_class(method_name, class_name)
        if resflag == 2:
            method_signature = ""
            method_type = method.get("type")
            if method_type == "name+signature":
                method_signature = method.get("signature")
            # message = f"Result of extract_method_from_class({method_name}, {class_name}):\n"
            message = ""
            message_add, candidate_list = self.construct_method_message(method_signature,
                                                                        extract_location=extract_location,
                                                                        append_to_extracted=True)
            if candidate_list:
                message += message_add
            else:
                message += "This method was not executed during the test, and no coverage information is available for this method."
            return message, candidate_list
        else:
            return message, []


    def _extract_method_from_class(self, method_name: str, class_name: str) -> (int, str):

        self.extract_methods_info.clear()
        # case 0 cannot find class
        if class_name not in self.classes_list:
            return 0, f"Cannot find class {class_name} in the codebase."
        candidate_files = []
        for file, class_list in self.file_classes_list.items():
            if class_name in class_list:
                candidate_files.append(file)

        for candidate_file in candidate_files:
            file_path = self.transform_file_path(candidate_file)
            with open(file_path, "r") as f:
                data = json.load(f)
            results = find_method_in_class(data, class_name, method_name)
            if not results:
                continue
            for r in results:
                parent_type = r["parent_type"]
                type = r["type"]
                flag = 0
                if type == "constructor":
                    flag = 2
                method_start_line = r["start_line"]
                method_end_line = r["end_line"]
                out = find_target_and_comments(os.path.join(self.codebase_path, candidate_file), method_name,
                                               method_start_line, flag)
                encoding = detect_file_encoding(os.path.join(self.codebase_path, candidate_file))
                method_content = out["content"]
                method_comment = clean_comment(out["comments"])
                node = find_method_node(os.path.join(self.codebase_path, candidate_file), method_name,
                                        method_start_line)
                if flag == 2:

                    signature = extract_signature_changed(node, encoding=encoding)
                else:
                    signature = extract_signature_changed(node, encoding=encoding)

                self.extract_methods_info.append(
                    {"method": method_name, "file": candidate_file, "start_line": method_start_line,
                     "end_line": method_end_line, "signature": signature, "comment": method_comment,
                     "parent_name": class_name, "parent_type": parent_type})

        if not self.extract_methods_info:
            # case 1 find class but cannot find method
            return 1, f"Cannot find method {method_name} in class {class_name}"

        else:
            # case 2 find class and method
            return 2, f"Find methods."

    def extract_method_from_file(self, method: Dict, raw_file: str, extract_location=False, from_codebase=False):
        if not from_codebase:
            append_to_extracted = True
        else:
            append_to_extracted = False
        raw_file = raw_file.strip()
        method_name = method.get("name")
        method_signature = ""
        method_type = method.get("type")
        if method_type == "name+signature":
            method_signature = method.get("signature")
        self.extract_methods_info.clear()
        self.find_possible_paths(raw_file)
        if not self.possible_paths_list:
            return f"Cannot find {raw_file} in the codebase.", []

        for file in self.possible_paths_list:
            file_path = self.transform_file_path(file)
            with open(file_path, "r") as f:
                data = json.load(f)

            results = find_all_methods_upgrade(data, method_name)
            if not results:
                continue
            for r in results:
                method_start_line = r["start_line"]
                method_end_line = r["end_line"]
                parent_name = r.get("parent_name")
                parent_type = r.get("parent_type")
                flag = 0
                if r['type'] == "constructor":
                    flag = 2

                out = find_target_and_comments(os.path.join(self.codebase_path, file), method_name,
                                               method_start_line, flag)

                encoding = detect_file_encoding(os.path.join(self.codebase_path, file))
                method_content = out["content"]
                method_comment = clean_comment(out["comments"])

                node = find_method_node(os.path.join(self.codebase_path, file), method_name,
                                        method_start_line)
                if flag == 2:
                    signature = extract_signature_changed(node, encoding=encoding)
                else:
                    signature = extract_signature_changed(node, encoding=encoding)
                self.extract_methods_info.append(
                    {"method": method_name, "file": file, "start_line": method_start_line, "end_line": method_end_line,
                     "signature": signature, "comment": method_comment, "parent_name": parent_name,
                     "parent_type": parent_type})

        if not self.extract_methods_info:
            return f"Cannot find method {method_name} in {raw_file}.", []
        message = ""
        message_add, candidate_list = self.construct_method_message(method_signature, extract_location=extract_location,
                                                                    append_to_extracted=append_to_extracted)
        if candidate_list:
            message += message_add
        else:
            message += "This method was not executed during the test, and no coverage information is available for this method."

        return message, candidate_list


    def extract_method_from_codebase(self, method: Dict):
        method_name = method.get("name")
        method_signature = ""
        method_type = method.get("type")
        if method_type == "name+signature":
            method_signature = method.get("signature")
        self.extract_methods_info.clear()
        extract_methods_info = []
        for file in self.java_file_relpaths:
            self.extract_method_from_file({"name": method_name, "type": "name"}, file, from_codebase=True)
            extract_methods_info.extend(self.extract_methods_info)

        if not extract_methods_info:
            return f"Cannot find method {method_name} in the codebase.", []

        # message = f"Result of extract_method_from_codebase({method_name}):\n"
        message = ""
        message_add, candidate_list = self.construct_method_message(method_signature, extract_methods_info,
                                                                    append_to_extracted=True)
        if candidate_list:
            message += message_add
        else:
            message += "This method was not executed during the test, and no coverage information is available for this method."
        # message += message_add
        return message, candidate_list

    def get_class_info_from_file(self, class_name: str, raw_file_path: str) -> str:
        self.extract_classes_info.clear()
        self.extract_methods_info.clear()
        class_name = class_name.strip()
        raw_file_path = raw_file_path.strip()
        class_name_extraction = class_name.split(".")[-1]
        class_name_extraction = class_name_extraction.split("$")[-1]
        package = False
        if class_name != class_name_extraction:
            package = True
        self.find_possible_paths(raw_file_path)
        if not self.possible_paths_list:
            return f"Cannot find {raw_file_path} in the codebase."

        Flag = False
        for file_path in self.possible_paths_list:
            for cn in self.file_classes_list[file_path]:
                if class_name_extraction == cn:
                    Flag = True
                    break

        imports = extract_imports(os.path.join(self.codebase_path, self.possible_paths_list[0]))
        if not Flag:

            if imports:
                import_stats = "\n".join(imports)
                return f"Cannot find the definition of {class_name_extraction} in {raw_file_path}. The imports of {self.possible_paths_list[0]} are:\n{import_stats}"
            else:
                return f"Cannot find the definition of {class_name_extraction} in {raw_file_path}"

        for file_path in self.possible_paths_list:
            imports = extract_imports(os.path.join(self.codebase_path, file_path))
            package_name = _get_package_name(os.path.join(self.codebase_path, file_path))
            file = self.transform_file_path(file_path)
            message = ""

            with open(file, "r") as f:
                data = json.load(f)
            result = self.find_class_in_file(data, class_name_extraction)
            if not result:
                continue
            actual_type = result["type"]
            flag = 1
            if actual_type == "interface":
                # print_and_log("get_class_info_from_file meet an interface!")
                flag = 3
            class_start_line = result["start_line"]
            class_end_line = result["end_line"]

            out = find_target_and_comments(os.path.join(self.codebase_path, file_path), class_name_extraction,
                                           class_start_line, flag)
            class_content = out["content"]
            class_comment = clean_comment(out["comments"])
            encoding = detect_file_encoding(os.path.join(self.codebase_path, file_path))
            children = extract_children_from_class(file_path, class_content, class_start_line, encoding,
                                                   actual_type=actual_type)
            extends, implements = extract_inheritance_info(class_content)
            inheritance = {}
            if extends:
                inheritance["extends"] = extends
            else:
                inheritance["extends"] = None
            if implements:
                inheritance["implements"] = implements
            else:
                inheritance["implements"] = None

            class_info_basic = {"file": file_path, "class": class_name_extraction, "start_line": class_start_line,
                                "end_line": class_end_line, "comment": class_comment, "imports": imports,
                                "package_name": package_name, "actual_type": actual_type}
            class_info = {**class_info_basic, **children, **inheritance}
            self.extract_classes_info.append(class_info)

        if not self.extract_classes_info:
            return f"Cannot find the definition of {class_name_extraction} in {raw_file_path}"
        if not package:
            # message = f"Result of get_class_info_from_file({class_name_extraction}, {raw_file_path}):\n"
            message = ""
        else:
            # message = f"Note that we can only search a class without the package name. Result of get_class_info_from_file({class_name_extraction}, {raw_file_path}):\n"
            message = "Note that we can only search a class without the package name.\n"
        construct_msg = self.construct_class_message()

        if construct_msg:
            message += construct_msg
        else:
            message += "The methods in this class were not executed during the test, and no coverage information is available for this class."

        return message

    def get_class_info_from_codebase(self, class_name: str) -> str:
        class_name = class_name.strip()
        # if ("." in class_name) or ("$" in class_name):
        #     print_and_log("get_class_info_from_codebase meet . or $ !")
        class_name_extraction = class_name.split(".")[-1]
        class_name_extraction = class_name_extraction.split("$")[-1]
        package = False
        if class_name != class_name_extraction:
            package = True
        self.extract_classes_info.clear()
        for file in self.java_file_relpaths:
            file_path = self.transform_file_path(file)
            with open(file_path, 'r') as f:
                data = json.load(f)
            result = self.find_class_in_file(data, class_name_extraction)
            if not result:
                continue
            actual_type = result["type"]
            flag = 1
            if actual_type == "interface":
                flag = 3
            class_start_line = result["start_line"]
            class_end_line = result["end_line"]
            out = find_target_and_comments(os.path.join(self.codebase_path, file), class_name_extraction,
                                           class_start_line, flag)
            class_content = out["content"]
            class_comment = clean_comment(out["comments"])
            encoding = detect_file_encoding(os.path.join(self.codebase_path, file))
            children = extract_children_from_class(file_path, class_content, class_start_line, encoding,
                                                   actual_type=actual_type)
            extends, implements = extract_inheritance_info(class_content)
            inheritance = {}
            if extends:
                inheritance["extends"] = extends
            else:
                inheritance["extends"] = None
            if implements:
                inheritance["implements"] = implements
            else:
                inheritance["implements"] = None

            imports = extract_imports(os.path.join(self.codebase_path, file))
            package_name = _get_package_name(os.path.join(self.codebase_path, file))
            class_info_basic = {"file": file, "class": class_name_extraction, "start_line": class_start_line,
                                "end_line": class_end_line, "comment": class_comment, "imports": imports,
                                "package_name": package_name, "actual_type": actual_type}
            class_info = {**class_info_basic, **children, **inheritance}
            self.extract_classes_info.append(class_info)

        if not self.extract_classes_info:
            return f"Cannot find class {class_name_extraction} in the codebase."
        if not package:
            # message = f"Result of get_class_info_from_codebase({class_name_extraction}):\n"
            message = ""
        else:
            # message = f"Note that we can only search a class without the package name. Result of get_class_info_from_codebase({class_name_extraction}):\n"
            message = "Note that we can only search a class without the package name.\n"
        construct_msg = self.construct_class_message()
        if construct_msg:
            message += construct_msg
        else:
            message += "The methods in this class were not covered during test execution, and no coverage information is available for this class."
        return message

    def construct_class_message(self):
        msg = ""
        covered_index = 0
        for item in self.extract_classes_info:
            target_file = os.path.join(self.codebase_path, item["file"])
            actual_type = item.get("actual_type")
            if actual_type is None:
                actual_type = "class"
                # print_and_log("actual_type is not set!")
            imports = item["imports"]
            class_name = item["class"]
            javadoc = item["comment"]
            extends = item["extends"]
            implements = item["implements"]
            fields = item["fields"]
            methods_info = item["methods_signature_list"]
            innerclasses_info = item["inner_classes"]
            innerinterfaces_info = item["inner_interfaces"]
            package_name = item["package_name"]

            covered_methods_info = self.clean_info(item["file"], methods_info)
            covered_innerclasses_info = self.clean_info(item["file"], innerclasses_info)
            covered_innerinterfaces_info = self.clean_info(item["file"], innerinterfaces_info)

            methods = []
            innerclasses = []
            innerinterfaces = []
            for method in covered_methods_info:
                methods.append(method["signature"])
            for innerclass in covered_innerclasses_info:
                innerclasses.append(innerclass["inner_class_name"])
            for innerinterface in covered_innerinterfaces_info:
                innerinterfaces.append(innerinterface["inner_interface_name"])

            if (methods or innerclasses or innerinterfaces) and len(self.extract_classes_info) > 1:
                covered_index += 1
                msg += f'({covered_index}) <file>{item["file"]}</file> <{actual_type}>{class_name}</{actual_type}>\n'
            elif (methods or innerclasses or innerinterfaces) and len(self.extract_classes_info) == 1:
                msg += f'<file>{item["file"]}</file> <{actual_type}>{class_name}</{actual_type}>\n'
            else:
                continue

            if package_name:
                msg += f'<package>{package_name}</package>\n'

            if extends:
                msg += f'<inherits>{extends}</inherits>\n'
            if implements:
                msg += f'<implements>\n'
                for interface in implements:
                    msg += f'{interface}\n'
                msg += '</implements>\n'

            if javadoc:
                msg += f'<comment>\n{javadoc}\n</comment>\n'
            if fields:
                msg += f'<fields>\n'
                for field in fields:
                    msg += f'{field}\n'
                msg += '</fields>\n'
            if methods:
                msg += f'<covered_methods>\n'
                if len(methods) > method_upper_bound:
                    msg += f'Too many methods, only show the first {method_upper_bound} methods.\n'
                    methods = methods[:method_upper_bound]
                for method in methods:
                    msg += f'{method}\n'
                msg += '</covered_methods>\n'
            if innerclasses:
                msg += f'<covered_inner_classes>\n'
                for innerclass in innerclasses:
                    msg += f'{innerclass}\n'
                msg += '</covered_inner_classes>\n'
            if innerinterfaces:
                msg += f'<covered_inner_interfaces>\n'
                for innerinterface in innerinterfaces:
                    msg += f'{innerinterface}\n'
                msg += '</covered_inner_interfaces>\n'

        return msg


    def get_files_from_dir(self, dir_path: str) -> str:
        """Implementation of the tool `get_covered_files_from_dir`."""

        dir_path = dir_path.strip()
        pre_msg = self.list_subdirectories(os.path.join(self.codebase_path, dir_path))
        if not "not exist" or "not a directory" in pre_msg:
            return pre_msg

        file_list = []
        for file in self.java_file_relpaths:
            if dir_path in file:
                file_list.append(file)
        if not file_list:
            if pre_msg:

                return f"There's no .java file under {dir_path}. The sub directories are: " + " ".join(pre_msg)
            else:
                return f"There's no .java file under {dir_path}."

        covered_file_list = self.clean_file_list(file_list)

        message = f"Result of get_covered_files_from_dir({dir_path}):\n"
        if not covered_file_list:
            message += f"There's no .java file under {dir_path} covered during execution."

        if len(covered_file_list) > files_from_dir_upper_bound:
            # covered_file_list = covered_file_list[:files_from_dir_upper_bound]
            covered_file_list = self.sort_by_line_coverage(covered_file_list, files_from_dir_upper_bound)
            message += f"Too many files, only show the first {files_from_dir_upper_bound} files with the highest line coverage.\n"
        message += "\n".join(covered_file_list)

        return message


    def get_inner_class_info(self, class_name: str, inner_class_name: str, file_path="") -> str:
        """Implementation of the tool `get_inner_class_info`."""

        message = f'Result of get_inner_class_info(class_name="{class_name}",inner_class_name="{inner_class_name}"):\n'
        class_name = class_name.strip()
        # if ("." in class_name) or ("$" in class_name):
        #     print_and_log("get_inner_class_info meet . or $ !")
        class_name_extraction = class_name.split(".")[-1]
        class_name_extraction = class_name_extraction.split("$")[-1]
        inner_class_name = inner_class_name.strip()
        if (class_name == ""):
            return message + "class_name cannot be empty. Please provide the name of the class."

        if inner_class_name == "":
            # return message + "Please provide the name of the inner class."
            inner_class_list = []
            inner_interface_list = []
            inner_class_str = ""
            inner_interface_str = ""
            if file_path:
                class_message = self.get_class_info_from_file(class_name, file_path)
            else:
                class_message = self.get_class_info_from_codebase(class_name)
            if "<covered_inner_classes>" in class_message:
                match = re.search(r'<covered_inner_classes>(.*?)</covered_inner_classes>', class_message, re.DOTALL)
                if match:
                    inner_class_str = match.group(1).strip()
                    inner_class_list = inner_class_str.split("\n")

            if "<covered_inner_interfaces>" in class_message:
                match = re.search(r'<covered_inner_interfaces>(.*?)</covered_inner_interfaces>', class_message,
                                  re.DOTALL)
                if match:
                    inner_interface_str = match.group(1).strip()
                    inner_interface_list = inner_interface_str.split("\n")

            if inner_class_str == "" and inner_interface_str == "":
                return message + "Cannot find any inner class or interface covered during test execution."
            else:
                if inner_class_str:
                    message += f"## Covered inner classes of {class_name_extraction}:\n{inner_class_str}\n\n"
                if inner_interface_str:
                    message += f"## Covered inner interfaces of {class_name_extraction}:\n{inner_interface_str}\n\n"

                return message + "** To get the information of a specific inner class or interface, please provide its name when calling `get_inner_class`."

        self.extract_classes_info.clear()
        self.extract_methods_info.clear()
        target_info = []
        find_class = False  # check whether we find the outer class
        find_interface = False
        flag = 1
        inner_type = "class"
        outer_type = "class"
        for file in self.java_file_relpaths:
            file_path = self.transform_file_path(file)
            with open(file_path, 'r') as f:
                data = json.load(f)

            result = self.find_class_in_file(data, class_name_extraction)
            if not result:
                continue
            outer_type = result["type"]
            if outer_type == "class":
                find_class = True
                flag = 1
            elif outer_type == "interface":
                find_interface = True
                flag = 3
            # print(result)
            class_start_line = result["start_line"]
            # print("this start",class_start_line)
            out = find_target_and_comments(os.path.join(self.codebase_path, file), class_name_extraction,
                                           class_start_line, flag)
            class_content = out["content"]
            encoding = detect_file_encoding(os.path.join(self.codebase_path, file))
            inner_class_content, inner_type, start_line, inner_class_byte_content = extract_innerclass_from_class(
                outer_type, class_content, inner_class_name, encoding=encoding)
            if inner_class_content != "":
                target_info.append({"file": file, "class": class_name_extraction, "inner_class": inner_class_name,
                                    "content": inner_class_content, "start_line": start_line + class_start_line - 1,
                                    "byte_content": inner_class_byte_content, "encoding": encoding})

        for t in target_info:
            t_content = t["byte_content"]
            t_file = t["file"]
            t_class_start = t["start_line"]
            t_covered_methods, t_field_list = self.iterate_inner_class(t_content, t_file, t_class_start,
                                                                       encoding=t["encoding"])
            t["covered_methods_info"] = t_covered_methods
            t["field_list"] = t_field_list

        if find_class or find_interface:
            if not target_info:
                return message + f"Cannot find {inner_class_name} in {class_name_extraction} in the codebase."

            if len(target_info) == 1:
                if len(target_info[0]["covered_methods_info"]) == 0:
                    # print_and_log("This can't happen! inner class has no covered method!")
                    return message + "This inner class was not covered during test execution, and no coverage information is available for this inner class."

                field_list = target_info[0]["field_list"]
                message += f"<file>{target_info[0]['file']}</file> <{outer_type}>{target_info[0]['class']}</class> <inner_{inner_type}>{target_info[0]['inner_class']}</inner_{inner_type}>\n"
                if field_list:
                    fields = "\n".join(field_list)
                    message += f"<fields>\n{fields}\n</fields>\n"

                covered_methods = ""
                count = 0
                for method in target_info[0]["covered_methods_info"]:
                    count += 1
                    method_content = read_lines_from_file_with_cov(os.path.join(self.codebase_path, method["file"]),
                                                                   method["start_line"], method["end_line"],
                                                                   method["covered_lines"])
                    covered_methods += f"##Method {count}:\n" + method_content + "\n"

                message += f"<covered_methods>\n{covered_methods}\n</covered_methods>\n"


            else:
                all_uncovered = True
                countnum = 0
                for info in target_info:
                    countnum += 1
                    if len(info["covered_methods_info"]) == 0:
                        continue
                    all_uncovered = False
                    message += f"({countnum}) <file>{info['file']}</file> <{outer_type}>{info['class']}</{outer_type}> <inner_{inner_type}>{info['inner_class']}</inner_{inner_type}>\n"
                    if info["field_list"]:
                        fields = "\n".join(info["field_list"])
                        message += f"<fields>\n{fields}\n</fields>\n"

                    covered_methods = ""
                    count = 0
                    for method in target_info[0]["covered_methods_info"]:
                        count += 1
                        method_content = read_lines_from_file_with_cov(os.path.join(self.codebase_path, method["file"]),
                                                                       method["start_line"], method["end_line"],
                                                                       method["covered_lines"])
                        covered_methods += f"##Method {count}:\n" + method_content + "\n"

                    message += f"<covered_methods>\n{covered_methods}\n</covered_methods>\n\n"

                if all_uncovered:
                    # print_and_log("This can't happen! inner class has no covered method!")
                    message += "This inner class was not executed during the test, and no coverage information is available for this inner class."

            return message
        else:
            return message + f"Cannot find {class_name_extraction} in the codebase."

    def recursively_find_method_start(self, data, target_method, start_line, parent_info=None):
        for item in data:
            if item['type'] == 'method' and (item['name'] in target_method) and item['start_line'] == start_line:
                return {
                    "method_info": item,
                    "parent_info": parent_info
                }
            if 'children' in item and item['children']:
                result = self.recursively_find_method_start(item['children'], target_method, start_line,
                                                            {"type": item['type'], "name": item['name']})
                if result:
                    return result
        return None

    def locate_method(self, file_path, start_line, end_line):
        encoding = detect_file_encoding(os.path.join(self.codebase_path, file_path))
        with open(os.path.join(self.codebase_path, file_path), 'r', encoding=encoding) as file:
            code = file.read()

        parser = Parser()
        parser.set_language(JAVA_LANGUAGE)
        tree = parser.parse(bytes(code, "utf8"))

        def walk_tree(node):
            results = []
            if node.type == 'method_declaration' or node.type == 'constructor_declaration':
                node_start = node.start_point[0] + 1
                node_end = node.end_point[0] + 1
                if node_start <= end_line and node_end >= start_line:
                    method_name = extract_method_name(node, code)
                    class_name = find_parent_class_name(node)
                    results.append({"method_name": method_name, "class_name": class_name, "node_start": node_start,
                                    "node_end": node_end})

            for child in node.children:
                results.extend(walk_tree(child))
            return results

        def extract_method_name(node, code):
            for child in node.children:
                if child.type == 'identifier':
                    return code[child.start_byte:child.end_byte]
            return "Unknown"

        def find_parent_class_name(node):
            current = node.parent
            while current:
                if current.type == 'class_declaration':
                    for child in current.children:
                        if child.type == 'identifier':
                            return code[child.start_byte:child.end_byte]
                current = current.parent
            return "Unknown"

        results = walk_tree(tree.root_node)
        return results

    def transform_file_path(self, file_path):
        return os.path.join(self.parse_files_path, file_path[:-5] + ".json")

    def find_class_in_file(self, data, class_name):
        for item in data:
            if (item['type'] == 'class' or item['type'] == 'interface') and item['name'] == class_name:
                return item
            if 'children' in item and item['children']:
                result = self.find_class_in_file(item['children'], class_name)
                if result:
                    return result

        return None

    def list_subdirectories(self, path):
        if not os.path.exists(path):
            rel_path = os.path.relpath(path, self.codebase_path)
            return f"The path '{rel_path}' does not exist."

        if not os.path.isdir(path):
            rel_path = os.path.relpath(path, self.codebase_path)
            return f"The path '{rel_path}' is not a directory."

        subdirectories = [d for d in os.listdir(path) if os.path.isdir(os.path.join(path, d))]
        return subdirectories

    def get_imports(self, file_path: str) -> str:
        """Implementation of the tool `get_imports`."""

        file_path = file_path.strip()
        msg = f"Result of get_imports({file_path}):\n"
        self.recognize_rel_path(file_path)
        if not self.possible_paths_list:
            return msg + f"The path '{file_path}' does not exist. Please check your input.\n"

        for fp in self.possible_paths_list:
            msg += f"File: {file_path}\n"
            abs_path = os.path.join(self.codebase_path, fp)
            res = _get_imports(abs_path)
            if not res:
                msg += f"No import statements are found in {file_path}."
            else:
                msg += "Import statements:\n"
                for imp in res:
                    msg += f"{imp}\n"

        return msg

    def recognize_rel_path(self, file_path):
        self.possible_paths_list.clear()
        abs_path = os.path.join(self.codebase_path, file_path)
        if not os.path.exists(abs_path):
            self.find_possible_paths(file_path)
        else:
            self.possible_paths_list.append(file_path)

    def find_path(self, file_path):
        file_path = file_path.strip()
        self.recognize_rel_path(file_path)
        return self.possible_paths_list

    def get_covered_lines(self, file_path, start_line, end_line):
        target_list = self.covered_line_src.get(file_path)
        if not target_list:
            target_list = self.covered_line_test.get(file_path)
            if not target_list:
                return []

        filter_target_list = []
        for number in target_list:
            if start_line <= number <= end_line:
                filter_target_list.append(number)
        return filter_target_list

    def iterate_inner_class(self, t_content, t_file, t_class_start, encoding='utf-8'):
        covered_methods = []
        methods_info_list, field_list = extract_info_from_innerclass(t_content, t_class_start, encoding=encoding)
        # print("class start:",t_class_start)
        # print(methods_info_list)
        for item in methods_info_list:
            start_line = item['start_line']
            end_line = item['end_line']
            covered_lines = self.get_covered_lines(t_file, start_line, end_line)
            if covered_lines:
                self.extracted_methods_list.append({"file": t_file, "start_line": start_line, "end_line": end_line})
                covered_methods.append(
                    {"file": t_file, "start_line": start_line, "end_line": end_line, "covered_lines": covered_lines})
        return covered_methods, field_list

    def reconstruct_method_message(self, filtered_list):
        message = ""
        for index, item in enumerate(filtered_list):

            message += f'\n({index + 1})'
            target_file = os.path.join(self.codebase_path, item["file"])
            start_line = item["start_line"]
            end_line = item["end_line"]
            signature = item["signature"]
            comment = item["comment"]
            javadoc_comment = clean_comment(comment)
            parent_type = item.get("parent_type")
            parent_name = item.get("parent_name")
            method_content = read_lines_from_file(target_file, start_line, end_line)
            item["code"] = method_content
            message += f'<file>{item["file"]}</file>'
            if parent_type and parent_name:
                message += f' <{parent_type}>{parent_name}</{parent_type}> '
            message += f'<method_signature>{signature}</method_signature>\n'
            if comment:
                message += f'<comment>\n{javadoc_comment}\n</comment>\n<code>\n{method_content}</code>\n'
            else:
                message += f'<code>\n{method_content}\n</code>\n'
        return message

    def remove_extracted_method(self, i):
        for item in self.extracted_methods_list:
            if item["file"] == i["file"] and item["start_line"] == i["start_line"] and item["end_line"] == i["end_line"]:
                self.extracted_methods_list.remove(item)
                return True

    def clean_file_list(self, file_list):
        covered_file_list = []
        for file in file_list:
            if (file in self.covered_line_src) or (file in self.covered_line_test):
                covered_file_list.append(file)
        return covered_file_list

    def sort_by_line_coverage(self, file_list, upper_bound):
        file_covered_line_count = {}
        for file in file_list:
            covered_line_list = self.covered_line_src.get(file)
            if not covered_line_list:
                covered_line_list = self.covered_line_test.get(file)
            if covered_line_list:
                file_covered_line_count[file] = len(covered_line_list)
            else:
                file_covered_line_count[file] = 0

        sorted_file_list = sorted(file_covered_line_count.items(), key=lambda x: x[1], reverse=True)
        return [file for file, _ in sorted_file_list[:upper_bound]]


def detect_file_encoding(file_path):
    with open(file_path, 'rb') as file:
        raw_data = file.read()
        result = chardet.detect(raw_data)
        encoding = result['encoding']
        # print(encoding)
    if encoding is None:
        encoding = 'utf-8'
    return encoding



def read_lines_from_file(file_path, start_line, end_line):
    """read a range of lines (star_line,end_line) from a file"""
    content = []
    encoding = detect_file_encoding(file_path)
    with open(file_path, 'r', encoding=encoding) as file:
        # with open(file_path, 'r', encoding='utf-8') as file:
        for current_line_number, line in enumerate(file, start=1):
            if int(start_line) <= current_line_number <= int(end_line):
                content.append(line)
            elif current_line_number > int(end_line):
                break
    return ''.join(content)


def find_method_in_class(data, class_name, method_name):
    results = []

    def recursive_search(data, class_name, method_name):
        for item in data:
            if (item['type'] == 'class' or item['type'] == 'interface') and item['name'] == class_name:
                for child in item['children']:
                    if (child['type'] == 'method' and child['name'] == method_name) or (
                            child['type'] == 'constructor' and child['name'] == method_name):
                        results.append(
                            {"start_line": child['start_line'], "end_line": child['end_line'], "type": child['type'],
                             "parent_type": item['type']})
                    if 'children' in child:
                        recursive_search(child['children'], class_name, method_name)
            elif 'children' in item:
                recursive_search(item['children'], class_name, method_name)

    recursive_search(data, class_name, method_name)
    return results


def find_all_methods(data, method_name):
    results = []
    for item in data:
        if (item['type'] == 'method' or item['type'] == 'constructor') and item['name'] == method_name:
            results.append({
                "start_line": item['start_line'],
                "end_line": item['end_line'],
                "type": item['type']
            })
        if 'children' in item:
            results.extend(find_all_methods(item['children'], method_name))
    return results


def find_all_methods_upgrade(data, method_name, parent=None):
    results = []
    for item in data:
        if (item['type'] == 'method' or item['type'] == 'constructor') and item['name'] == method_name:
            result = {
                "start_line": item['start_line'],
                "end_line": item['end_line'],
                "type": item['type']
            }
            if parent:
                result["parent_name"] = parent['name']
                result["parent_type"] = parent['type']
            results.append(result)
        if 'children' in item:
            results.extend(find_all_methods_upgrade(item['children'], method_name, parent=item))
    return results



