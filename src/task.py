import os
import time
from pathlib import Path
from src.custom_signal import TaskMainNormalExit, TaskMainErrorExit
from src.tools.auxiliary import find_class_from_file, is_abstract_method
from src.codebase import CodeBase
from loguru import logger
from src.record import print_and_log
from src.prompt import fl_agent_system_with_tools, fl_agent_user_with_tools_first, \
    analyse_result, fl_agent_user_with_tools_second, fl_agent_user_with_tools_upgrade, \
    fl_agent_final_bug_location, proj_introduction, error_info_note, \
    sort_buggy_methods, recheck, fl_agent_user_with_tools_first_without_issue_analysis, \
    fl_agent_user_with_tools_upgrade_no_review_result, fl_agent_final_bug_location_no_review_result, \
    fl_agent_user_with_tools_second_no_review_result, \
    location_double_ask_force
from src.models.GPT import Model
from src.message import MessageRecord
import json
from src.tools.tools_invoker import ToolsInvoker, get_tools_list
from src.parse.parse_repo import process_java_files
from src.parse.parse_summary import generate_summary
from src.dataset.repo_d4j import recognize_pattern
from src.tools.utils import inspect_tools, extract_method_name, split_methods
input_tokens_sum = 0
output_tokens_sum = 0


def extract_json_from_response(res_content):
    try:
        res_dict = json.loads(res_content)

    except json.decoder.JSONDecodeError:
        return 0, None
    return 1, res_dict


def get_bl_output(bug_file, bug_class, bug_method, bug_codebase, tools_collect: ToolsInvoker, codebase_path,
                  proj_test_pattern_begin):
    """Location Extraction."""

    filtered_candidate_list = []
    output = ""
    if (not bug_file) or (not bug_class) or (not bug_method):
        output = "The bug location is not precise enough to be extracted. Please write down a location with file path, class and method name."
    else:
        # First, check if the file exists.
        bug_file = bug_file.strip()
        bug_class = bug_class.strip()
        bug_method = bug_method.strip()
        possible_file_list = bug_codebase.find_path(bug_file)

        if len(possible_file_list) == 0:
            output = f"The bug location is not precise enough to be extracted. `{bug_file}` does not exist in the codebase. Please check if the path is correct."
        elif len(possible_file_list) > 1:
            candidate_path = ""
            for path in possible_file_list:
                candidate_path += "\n" + path
            output = f"The bug location is not precise enough to be extracted. For `{bug_file}`, we found these possible paths: {candidate_path}."
        else:
            bug_file = possible_file_list[0]
            if bug_file.startswith(proj_test_pattern_begin):
                output = f"`{bug_file}` is in the test directory but bug locations should be in the source directory. "
            else:
                abs_path = os.path.join(codebase_path, bug_file)
                if os.path.isdir(abs_path):
                    output = f"The bug location is not precise enough to be extracted.`{bug_file}` is a directory."

                else:
                    flag, *_ = find_class_from_file(os.path.join(codebase_path, bug_file), bug_class)
                    if flag == 0:
                        output = f"The bug location is not precise enough to be extracted. Cannot find `{bug_class}` in `{bug_file}`."
                    else:
                        output, candidate_list = tools_collect.extract_method_from_class(bug_method, bug_class,
                                                                                         extract_location=True)
                        if candidate_list is not None:

                            for item in candidate_list:
                                if item.get("file") == bug_file:
                                    filtered_candidate_list.append(item)

                        if not filtered_candidate_list:
                            # can find file and class but no method
                            output = f"The bug location is not precise enough to be extracted. The class `{bug_class}` in `{bug_file}` has been identified, but the method `{bug_method}` could not be found as a covered method during the execution of this test."

    return bug_file, bug_class, bug_method, output, filtered_candidate_list


def update_tokens(add_input, add_output):
    global input_tokens_sum, output_tokens_sum
    input_tokens_sum += add_input
    output_tokens_sum += add_output


def detect_constructor(bug_method, bug_class):
    if "<init>" in bug_method:
        return bug_method.replace("<init>", bug_class.strip(), 1)
    if "<constructor>" in bug_method:
        return bug_method.replace("<constructor>", bug_class.strip(), 1)
    return bug_method


def extract_sorted_methods(bug_locations, res_dict):
    sorted_methods = res_dict["ranked_methods"]
    sorted_methods_list = []
    for method in sorted_methods:
        index = method["index"]
        level = method["level"]
        if index <= len(bug_locations):
            loc = bug_locations[index - 1]

            if not check_exist(loc, sorted_methods_list):
                loc["level"] = level
                sorted_methods_list.append(loc)

    sorted_methods_list.sort(key=lambda x: x["level"])
    return sorted_methods_list


def recheck_loc(bug_locations, extracted_methods_list):
    """Check if the bug locations need to be rechecked."""
    bugs_to_recheck = len(bug_locations)
    for loc in bug_locations:
        for method in extracted_methods_list:
            if loc["file"] == method["file"] and loc["start_line"] == method["start_line"] and loc["end_line"] == \
                    method["end_line"]:
                bugs_to_recheck -= 1
                break
    if bugs_to_recheck == 0:
        return False
    else:
        return True


def remove_from_bug_locations(bug_locations, file, class_name, signature):
    end_line = None
    for loc in bug_locations:
        if loc["file"] == file and loc["class"] == class_name and loc["signature"] == signature:
            end_line = loc["end_line"]
            bug_locations.remove(loc)
            break
    return end_line


def check_exist(element, locs):
    for loc in locs:
        if "end_line" in loc:
            if element["file"] == loc["file"] and element["end_line"] == loc["end_line"]:
                return True
    return


def remove_from_partial_correct_loc(partial_correct_loc, file, end_line):
    for loc in partial_correct_loc:
        if loc["file"] == file and loc["end_line"] == end_line:
            partial_correct_loc.remove(loc)
            print_and_log("Remove from partial correct loc.")
            break


def remove_duplicate(bug_locations):
    recorded_loc = []
    new_bug_locations = []
    for loc in bug_locations:
        loc_file = loc["file"]
        loc_end_line = loc["end_line"]
        if (loc_file, loc_end_line) not in recorded_loc:
            recorded_loc.append((loc_file, loc_end_line))
            new_bug_locations.append(loc)
    return new_bug_locations


def construct_buggy_loc(bug_locations):
    if len(bug_locations) > 1:
        bug_locations_res = "Here are the methods extracted from the final suspicious locations:"
    elif len(bug_locations) == 1:
        bug_locations_res = "Here is the method extracted from the final suspicious location"
    else:
        bug_locations_res = ""
    for i, item in enumerate(bug_locations):
        bug_locations_res += f"\nBug Location {i + 1}:" + f'<file>{item["file"]}</file> <class>{item["class"]}</class> \n<comment>\n{item["comment"]}\n</comment>\n<signature>{item["signature"]}</signature>\n<code>\n{item["code"]}\n</code>\n'
    return bug_locations_res

def run(parsed_dir, FL_round_upperbound, temperature, model_type, bug_id, bug_output_dir, trigger_test_info, codebase_path, trigger_test, advanced_identification=False, re_check=False, partial_save=False, issue_analysis=True, review_result=True, location_extraction_flag=True):
    bug_input_tokens_sum = 0
    bug_output_tokens_sum = 0

    def bug_update_tokens(add_input, add_output):
        nonlocal bug_input_tokens_sum, bug_output_tokens_sum
        bug_input_tokens_sum += add_input
        bug_output_tokens_sum += add_output

    time_start = time.time()

    functions_call_record = []
    log_handler_id = logger.add(os.path.join(bug_output_dir, "record.log"),
                                level="INFO",
                                format=(
                                    "<cyan>{time:YYYY/MM/DD - HH:mm:ss.SSS}</cyan> | <magenta>{level: ^10}</magenta>"
                                    " | <level>{message}</level>"
                                ),
                                )
    print_and_log(
        f"============= Running task {bug_id} =============",
    )

    print_and_log("Tool invocation loop upper limit: " + str(FL_round_upperbound + 1))

    proj_main_pattern, proj_test_pattern = recognize_pattern(codebase_path)
    if (not proj_main_pattern) or (not proj_test_pattern):
        print_and_log(
            "Failed to recognize the source and test folders. The codebase for this bug may not have been checked out correctly. You may need to check if Defects4J can check out correctly.\n")
        raise TaskMainErrorExit(
            f"Error exit for {bug_id}: Failed to recognize the source and test folders. The codebase for this bug may not have been checked out correctly. You may need to check if Defects4J can check out correctly.\n")
    else:
        proj_test_pattern_begin = proj_test_pattern
        proj_main_pattern += "..."
        proj_test_pattern += "..."

    message_record = MessageRecord()
    func_call_record_all = []
    bug_locations = []
    top_1_buggy = {}
    sorted_methods = []
    recheck_conduct = False  # if self-check is needed
    try:

        agent_base = Model()
        agent_base.initial_model_config(model_type)
        test_src = trigger_test_info["src"]
        test_path = trigger_test_info["path"]
        test_error_info = trigger_test_info["clean_error_info"]

        print_and_log("============= Running fl-agent =============")

        early_stop = False

        message_record.add_msg("system",
                           fl_agent_system_with_tools.format(proj_usage=proj_introduction[bug_id.split("-")[0]],
                                                             proj_main=proj_main_pattern,
                                                             proj_test=proj_test_pattern))

        print_and_log("system prompt:\n" + message_record.get_last_msg()["content"])

        fl_user_prompt = f"Failing Test Case Info:\nTest Path:\n{test_path}\n\nTest Source Code:\n{test_src}\n\nTest Error Information:\n{test_error_info}\n\n" + \
                         error_info_note[bug_id.split("-")[0]]
        if issue_analysis is True:

            fl_user_prompt +="\n\nPlease analyse the issue based on the provided test case error information. Address the analysis in three steps:\n### Analysis of the Test Failure\n### Potential Cause of the Issue\n### Suggested Starting Points for Root Cause Investigation."


            message_record.add_msg("user", fl_user_prompt)
            print_and_log("initial issue analysis:\n" + message_record.get_last_msg()["content"])
            res, res_content, raw_tool_calls, function_calls, input_tokens, output_tokens = agent_base.call(
                message_record.get_msgs(),temp=temperature)
            update_tokens(input_tokens, output_tokens)
            bug_update_tokens(input_tokens, output_tokens)
            print_and_log("res_content:\n" + res_content)
            message_record.add_assistant_msg(res_content, [])
        if issue_analysis is True:
            message_record.add_msg("user", fl_agent_user_with_tools_first)
        else:
            message_record.add_msg("user",fl_user_prompt + fl_agent_user_with_tools_first_without_issue_analysis)
        parsed_files_path = os.path.join(parsed_dir, bug_id, "result")
        parsed_summary = os.path.join(parsed_dir, bug_id, "summary", "summary.json")
        if not os.path.exists(parsed_files_path):
            process_java_files(codebase_path, parsed_files_path)
        if not os.path.exists(parsed_summary):
            generate_summary(codebase_path, os.path.join(parsed_dir, bug_id, "summary"))

        bug_codebase = CodeBase(codebase_path,
                                parsed_files_path)
        bug_codebase.load_parsed_files(parsed_summary)
        bug_codebase.read_covered_info(bug_id.split("-")[0],bug_id.split("-")[1],trigger_test)
        tools_collect = ToolsInvoker(bug_codebase)
        fl_tools = get_tools_list()
        # Prepare tool descriptions in the required format
        tools = ToolsInvoker.generate_tool_calls_data(fl_tools)
        print_and_log("start the tool invocation loop.")
        print_and_log("prompt:\n" + message_record.get_last_msg()["content"])
        res, res_content, raw_tool_calls, function_calls, input_tokens, output_tokens = agent_base.call(
            message_record.get_msgs(), tools=tools, temp=temperature)
        update_tokens(input_tokens, output_tokens)
        bug_update_tokens(input_tokens, output_tokens)
        # print_and_log(res)
        print_and_log("res_content:" + res_content)
        message_record.add_assistant_msg(res_content, raw_tool_calls)
        print_and_log("tool_calls:")
        for item in function_calls:
            print_and_log(item)
        if function_calls:
            func_res_list, error_info_list, func_call_record = tools_collect.extract_tool_calls(function_calls)
            func_call_record_all.append(func_call_record)

            find_cov_annotation = False
            if func_res_list:
                for res in func_res_list:
                    if "//**covered**" in res["content"]:
                        find_cov_annotation = True
                    message_record.add_tool_res(res["content"], res["func_id"])
            if error_info_list:
                for error in error_info_list:
                    message_record.add_tool_res(error["content"], error["func_id"])

            if func_res_list or error_info_list:
                conversation_log = Path(bug_output_dir, f"conversation-temp.json")
                conversation_log.write_text(json.dumps(message_record.get_msgs(), indent=4))
                if review_result:
                    if not find_cov_annotation:
                        message_record.add_msg("user", analyse_result)
                    else:
                        note = "\n## Note:\nIn an extracted method, the code line annotated with `//**covered**` is the code line that is covered during the execution of the test case.\n In contrast, the code line in a method without this annotation is not covered."
                        message_record.add_msg("user", analyse_result + note)
                    print_and_log("prompt:\n" + message_record.get_last_msg()["content"])
                    res, res_content, raw_tool_calls, function_calls, input_tokens, output_tokens = agent_base.call(
                        message_record.get_msgs(), temp=temperature)
                    update_tokens(input_tokens, output_tokens)
                    bug_update_tokens(input_tokens, output_tokens)
                    print(res)
                    print_and_log("analysis:\n" + res_content)
                    message_record.add_assistant_msg(res_content, [])

                current_round = 0
                global FL_break
                FL_break = False
                block_fl_ask = False
                special_fl_block = False
                bug_locations_extracted = False
                partial_correct_loc = []

                root_cause = ""
                while current_round <= FL_round_upperbound and (not early_stop):
                    if (((not block_fl_ask) and (not special_fl_block)) or current_round == FL_round_upperbound):
                        retry = 0
                        if review_result:
                            if current_round != FL_round_upperbound:
                                message_record.add_msg("user",
                                                   fl_agent_user_with_tools_upgrade.format(proj_main=proj_main_pattern,
                                                                                           proj_test=proj_test_pattern))

                            else:

                                message_record.add_msg("user", fl_agent_final_bug_location.format(proj_main=proj_main_pattern,
                                                                                          proj_test=proj_test_pattern))
                        else:

                            if current_round != FL_round_upperbound:
                                message_record.add_msg("user",
                                                       fl_agent_user_with_tools_upgrade_no_review_result.format(proj_main=proj_main_pattern,
                                                                                               proj_test=proj_test_pattern))
                            else:
                                message_record.add_msg("user", fl_agent_final_bug_location_no_review_result.format(proj_main=proj_main_pattern,
                                                                                          proj_test=proj_test_pattern))
                        while (retry < 3):
                            print_and_log("prompt:\n" + message_record.get_last_msg()["content"])
                            res, res_content, raw_tool_calls, function_calls, input_tokens, output_tokens = agent_base.call(
                                message_record.get_msgs(), response_format="json_object", temp=temperature)
                            print_and_log("res_content:")
                            print_and_log(res_content)
                            update_tokens(input_tokens, output_tokens)
                            bug_update_tokens(input_tokens, output_tokens)
                            flag, res_dict = extract_json_from_response(res_content)
                            if flag == 0:
                                retry += 1
                                continue
                            # buglocations: [Dict]
                            bug_locations = res_dict.get("bug_locations")
                            root_cause = res_dict.get("root_cause")
                            if bug_locations:
                                FL_break = True
                                message_record.add_assistant_msg(res_content, [])
                            else:
                                if current_round == FL_round_upperbound:
                                    message_record.add_assistant_msg(res_content,[])
                                else:
                                    message_record.remove_last_msg()
                            break
                            # example
                        #    "bug_locations": [
                        #         {
                        #             "file":
                        #                 "src/main/java/org/apache/commons/lang3/math/NumberUtils.java",
                        #             "class": "NumberUtils",
                        #             "method": "createNumber(String)"
                        #         }
                        #     ],
                        #     "root_cause": "The createNumber(String) method in the NumberUtils class does not handle parsing of hexadecimal numbers such as '0Xfade'."
                        # }

                        if FL_break:
                            partial_fail = False
                            print_and_log("============= Bug Location Extraction =============")
                            location_extractions = []
                            location_extraction_list = []
                            for bug_loc in bug_locations:
                                print_and_log("bug_loc:\n")
                                print_and_log(bug_loc)
                                if isinstance(bug_loc, dict):
                                    bug_file = bug_loc.get("file")
                                    bug_class = bug_loc.get("class")
                                    bug_class = bug_class.split(".")[-1]
                                    bug_class = bug_class.split("$")[-1]
                                    bug_method = bug_loc.get("method")

                                    bug_method = detect_constructor(bug_method, bug_class)

                                    candidate_list = []
                                    bug_file, bug_class, bug_method, output, candidate_list = get_bl_output(
                                        bug_file, bug_class, bug_method, bug_codebase, tools_collect, codebase_path,
                                        proj_test_pattern_begin)

                                    location_extractions.append(output)
                                    if not candidate_list:
                                        location_extraction_list.append([])
                                    else:
                                        location_extraction_list.append(candidate_list.copy())

                                else:
                                    print_and_log("This bug_loc is not a dict!!!!!")
                            double_ask = []

                            if (current_round == FL_round_upperbound) or (location_extraction_flag == False):
                                location_extractions_temp = []
                                location_extraction_list_temp = []
                                bug_locations_temp = []
                                for i, loc in enumerate(location_extractions):
                                    if (("The bug location is not precise enough" in loc) or (
                                            "Cannot find" in loc) or (
                                            "The method name is invalid" in loc) or (
                                            "is in the test directory but" in loc)):
                                        print_and_log("Force:not precise enough.")
                                        print_and_log(loc)
                                        continue
                                    else:
                                        location_extractions_temp.append(loc)
                                        location_extraction_list_temp.append(location_extraction_list[i])
                                        bug_locations_temp.append(bug_locations[i])
                                location_extractions = location_extractions_temp
                                location_extraction_list = location_extraction_list_temp
                                bug_locations = bug_locations_temp
                                if not location_extractions and current_round == FL_round_upperbound:
                                    print_and_log("Force:All bug locations are not precise enough to be extracted.")
                                elif (not location_extractions) and (not location_extraction_flag):
                                    print_and_log("actively write locations: All bug locations are not precise enough to be extracted.")

                            for i, loc in enumerate(location_extractions):
                                if location_extraction_flag:
                                    if (("The bug location is not precise enough" in loc) or ("Cannot find" in loc) or (
                                            "The method name is invalid" in loc) or (
                                            "is in the test directory but" in loc)) and (current_round < FL_round_upperbound) :
                                        if ("The bug location is not precise enough" in loc) or (
                                                "is in the test directory but" in loc):

                                            message_record.add_msg("user",
                                                                   loc + " You may need to search more information to provide a more precise method-level bug location.")
                                        elif "Cannot find" in loc:
                                            message_record.add_msg("user",
                                                                   "Cannot find the method. The provided method, class, or file information might not match. You may need to search for more information to provide a more precise method-level bug location.")

                                        elif "The method name is invalid" in loc:
                                            message_record.add_msg("user",
                                                                   "The method name is invalid. You may need to search more information to provide a precise method-level bug location.")

                                        FL_break = False
                                        double_ask = []
                                        if partial_save:
                                            partial_fail = True
                                        else:
                                            break

                                location_extraction = location_extraction_list[i]

                                if len(location_extraction) > 1:
                                    double_ask.append(i + 1)
                                elif len(location_extraction) == 1:

                                    bug_locations[i]["comment"] = location_extraction[0]["comment"]
                                    bug_locations[i]["code"] = location_extraction[0]["code"]
                                    bug_locations[i]["start_line"] = location_extraction[0]["start_line"]
                                    bug_locations[i]["end_line"] = location_extraction[0]["end_line"]
                                    bug_locations[i]["file"] = location_extraction[0]["file"]
                                    bug_locations[i]["class"] = location_extraction[0]["parent_name"]
                                    bug_locations[i]["method"] = location_extraction[0]["method"]
                                    bug_locations[i]["signature"] = location_extraction[0]["signature"]
                                    check_abstract = is_abstract_method(bug_locations[i]["code"])
                                    if check_abstract and (not partial_fail):
                                        message_record.add_msg("user",
                                                               f'''{bug_locations[i]["method"]} in class {bug_locations[i]["class"]} in file {bug_locations[i]["file"]} is an abstract method. ''' + " You may need to search more information to provide a more precise method-level bug location.")
                                        FL_break = False

                            if double_ask and (not partial_fail) and FL_break:
                                FL_break = False
                                reask_try = 0
                                while reask_try < 3:
                                    double_ask_str = [str(number) for number in double_ask]
                                    begin = "The bug locations " + ",".join(
                                        double_ask_str) + " have multiple candidate locations. Please provide the index of the real buggy location. For each bug that needs to be reselected, provide the file, class, method, and candidate index in the following JSON format:\n"
                                    ans_form = '''\n{
          \"reselected_bug_locations\": [
            {
              \"file\": \"path/to/file\",
              \"class\": \"class_name\",
              \"method\": \"method_name\"
              \"candidate_index\": 1
            },
            {
              \"file\": \"path/to/another/file\",
              \"class\": \"another_class_name\",
              \"method\": \"another_method_name\",
              \"candidate_index\": 2
            }
            ...
          ]
        }
        \nHere are the candidate locations:\n'''
                                    ans_form_single = '''\n{
                                      \"reselected_bug_locations\": [
                                        {
                                          \"file\": \"path/to/file\",
                                          \"class\": \"class_name\",
                                          \"method\": \"method_name\"
                                          \"candidate_index\": <positive integer representing the index number>
                                        }
                                      ]
                                    }
                                    \nHere are the candidate locations:\n'''

                                    content = ""
                                    for reask_loc in double_ask:
                                        loc = location_extractions[reask_loc - 1]
                                        content += f"\nLocation {reask_loc}:\n" + "\n".join(split_methods(loc))

                                    end = "\nPlease return the JSON object with the correct candidate indices.\n"
                                    if len(double_ask) == 1:
                                        reask_msg = begin + ans_form_single + content + end
                                    else:
                                        reask_msg = begin + ans_form + content + end

                                    abstract_exist = False
                                    message_record.add_msg("user", reask_msg)

                                    print_and_log("prompt:\n" + message_record.get_last_msg()["content"])
                                    res, res_content, raw_tool_calls, function_calls, input_tokens, output_tokens = agent_base.call(
                                        message_record.get_msgs(), response_format="json_object", temp=temperature)

                                    message_record.remove_last_msg()
                                    print_and_log("res_content:")
                                    print_and_log(res_content)
                                    update_tokens(input_tokens, output_tokens)
                                    bug_update_tokens(input_tokens, output_tokens)
                                    flag, res_dict = extract_json_from_response(res_content)
                                    if flag == 0 or ("reselected_bug_locations" not in res_dict):
                                        reask_try += 1
                                        continue

                                    reselected_bug_locations = res_dict['reselected_bug_locations']


                                    for bug in reselected_bug_locations:
                                        remove_index = -1
                                        file = bug['file'].strip()
                                        class_name = bug['class'].strip()
                                        class_name = class_name.split(".")[-1]
                                        class_name = class_name.split("$")[-1]
                                        method_name = bug['method'].strip()
                                        method_name = extract_method_name(method_name)
                                        candidate_index = bug['candidate_index']
                                        for index in double_ask:
                                            index -= 1
                                            loc_list = location_extraction_list[index]
                                            for i, item in enumerate(loc_list):
                                                item_file = item["file"]
                                                item_class = item.get("parent_name")
                                                item_method = item["method"]
                                                if ((file == item_file) or (
                                                        file in item_file)) and class_name == item_class and method_name == item_method and (
                                                        i + 1) == candidate_index:
                                                    bug_locations[index]["comment"] = item["comment"]
                                                    bug_locations[index]["code"] = item["code"]
                                                    bug_locations[index]["start_line"] = item["start_line"]
                                                    bug_locations[index]["end_line"] = item["end_line"]
                                                    bug_locations[index]["class"] = class_name
                                                    bug_locations[index]["signature"] = item["signature"]
                                                    bug_locations[index]["method"] = method_name
                                                    bug_locations[index]["file"] = item_file
                                                    remove_index = index + 1
                                                    check_abstract = is_abstract_method(
                                                        bug_locations[index]["code"])
                                                    if check_abstract:
                                                        message_record.add_msg("user",
                                                                               f'''{item_method} in class {item_class} in file {item_file} is an abstract method. ''' + " You may need to search more information to provide a more precise method-level bug location.")
                                                        FL_break = False
                                                        abstract_exist = True
                                                        break

                                                    break

                                            if abstract_exist:
                                                break

                                            if remove_index != -1:
                                                double_ask.remove(remove_index)
                                                break

                                    if double_ask and (not abstract_exist):
                                        print_and_log("select candidates again.")
                                        print_and_log(double_ask)
                                        reask_try += 1
                                        if reask_try == 3:
                                            print_and_log("inquired several times but still haven't received any clear locations\n")
                                        continue
                                    else:
                                        if not abstract_exist:
                                            FL_break = True

                                        break

                            if partial_save and partial_fail:
                                print_and_log("Try to save partially correct location.")
                                for element in bug_locations:
                                    if element.get("end_line") and element.get("file"):
                                        if not check_exist(element,partial_correct_loc):
                                            partial_correct_loc.append(element)
                                FL_break = False
                            if FL_break:
                                for element in partial_correct_loc:
                                    if not check_exist(element, bug_locations):
                                        print_and_log("Add partially correct location(s) to bug locations.")
                                        bug_locations.append(element)

                                bug_locations = remove_duplicate(bug_locations)

                                with open(os.path.join(bug_output_dir, f'{bug_id}.json'), 'w') as file:
                                    json.dump(bug_locations, file, indent=4)
                                with open(os.path.join(bug_output_dir, "root_cause.txt"), 'w') as file:
                                    file.write(root_cause)


                                bug_locations_extracted = True
                                if current_round == FL_round_upperbound and not bug_locations:
                                    bug_locations_extracted = False
                                    break
                                bug_locations_res = ""


                                if location_extraction_flag:

                                    if len(bug_locations) > 1:
                                        bug_locations_res = "Here are the code of the bug locations:"
                                    elif len(bug_locations) == 1:
                                        bug_locations_res = "Here is the code of the bug location:"
                                    for i, item in enumerate(bug_locations):
                                        bug_locations_res += f"\nBug Location {i + 1}:" + f'<file>{item["file"]}</file> <class>{item["class"]}</class> \n<comment>\n{item["comment"]}\n</comment>\n<signature>{item["signature"]}</signature>\n<code>\n{item["code"]}\n</code>\n'
                                    message_record.add_msg("user", bug_locations_res)

                                    extracted_methods_list = bug_codebase.get_extracted_methods_list()
                                    print_and_log("extracted_methods_list:")
                                    print_and_log(extracted_methods_list)
                                    # Self-check
                                    if recheck_loc(bug_locations, extracted_methods_list) and re_check:
                                        recheck_conduct = True
                                        last_msg = message_record.get_last_msg()
                                        message_record.remove_last_msg()
                                        new_msg = last_msg["content"] + "\n" + recheck
                                        message_record.add_msg("user", new_msg)
                                        print_and_log("prompt:\n"+new_msg)
                                        retry = 0
                                        recheck_list = None
                                        while retry < 3:
                                            res, res_content, raw_tool_calls, function_calls, input_tokens, output_tokens = agent_base.call(
                                                message_record.get_msgs(), response_format="json_object",
                                                max_tokens=1024, temp=temperature)
                                            update_tokens(input_tokens, output_tokens)
                                            bug_update_tokens(input_tokens, output_tokens)
                                            print_and_log("conditional self-reflection:")
                                            print_and_log(res_content)
                                            flag, res_dict = extract_json_from_response(res_content)
                                            if flag == 0:
                                                retry += 1
                                                continue

                                            recheck_list = res_dict.get("recheck")
                                            if recheck_list:
                                                break
                                        for element in recheck_list:
                                            if element["buggy"] == False:
                                                end_line = remove_from_bug_locations(bug_locations, element["file"],
                                                                          element["class"], element["signature"])
                                                if end_line:
                                                    remove_from_partial_correct_loc(partial_correct_loc, element["file"],
                                                                                end_line)
                                                print_and_log("Remove location from bug locations.")


                                        if len(bug_locations) <= 0:
                                            FL_break = False
                                            bug_locations_extracted = False
                                            message_record.add_assistant_msg(res_content, [])
                                            with open(os.path.join(bug_output_dir, f'{bug_id}.json'),
                                                      'w') as file:
                                                json.dump([], file, indent=4)


                                        else:

                                            bug_locations = remove_duplicate(bug_locations)
                                            message_record.add_assistant_msg(res_content, [])
                                            with open(os.path.join(bug_output_dir, f'{bug_id}.json'),
                                                      'w') as file:
                                                json.dump(bug_locations, file, indent=4)
                                            with open(os.path.join(bug_output_dir, "root_cause.txt"),
                                                      'w') as file:
                                                file.write(root_cause)
                                            break

                                    else:
                                        # print_and_log("There's no need for self-reflection.")
                                        print_and_log("There's no need for self-check.")
                                        recheck_conduct = False
                                        break
                                else:
                                    break

                    if special_fl_block:
                        special_fl_block = False

                    current_round += 1

                    if current_round > FL_round_upperbound:
                        break
                    if review_result:
                        message_record.add_msg("user", fl_agent_user_with_tools_second)
                    else:

                        message_record.add_msg("user", fl_agent_user_with_tools_second_no_review_result)
                    print_and_log("prompt:\n" + message_record.get_last_msg()["content"])
                    res, res_content, raw_tool_calls, function_calls, input_tokens, output_tokens = agent_base.call(
                        message_record.get_msgs(), tools=tools, temp=temperature)
                    update_tokens(input_tokens, output_tokens)
                    bug_update_tokens(input_tokens, output_tokens)
                    print_and_log("res_content:\n" + res_content)
                    if raw_tool_calls is None:
                        raw_tool_calls = []
                    print_and_log("function_calls:")
                    print_and_log(function_calls)
                    if raw_tool_calls:
                        raw_tool_calls = inspect_tools(raw_tool_calls)

                    if (not raw_tool_calls) and (not res_content):
                        # The agent most likely called a tool that does not meet the specifications.
                        message_record.remove_last_msg()
                        special_fl_block = True
                        continue
                    message_record.add_assistant_msg(res_content, raw_tool_calls)
                    if res_content:
                        block_fl_ask = False
                    if not function_calls:
                        print_and_log("FL agent doesn't call any function.")
                        block_fl_ask = False
                        continue
                    else:
                        func_res_list, error_info_list, func_call_record = tools_collect.extract_tool_calls(function_calls)
                        func_call_record_all.append(func_call_record)

                        find_cov_annotation = False
                        if func_res_list:
                            for res in func_res_list:
                                if "//**covered**" in res["content"]:
                                    find_cov_annotation = True

                                message_record.add_tool_res(res["content"], res["func_id"])
                        if error_info_list:
                            for error in error_info_list:
                                message_record.add_tool_res(error["content"], error["func_id"])

                        if func_res_list or error_info_list:
                            # Save the temporary file for the conversation
                            conversation_log = Path(bug_output_dir, f"conversation-temp.json")
                            conversation_log.write_text(json.dumps(message_record.get_msgs(), indent=4))
                            if review_result:
                                if find_cov_annotation:
                                    note = "\n## Note:\nIn an extracted method, the code line annotated with `//**covered**` is the code line that is covered during the execution of the test case.\n In contrast, the code line in a method without this annotation is not covered."
                                    message_record.add_msg("user", analyse_result+note)
                                else:
                                    message_record.add_msg("user", analyse_result)

                                print_and_log("prompt:\n" + message_record.get_last_msg()["content"])
                                res, res_content, raw_tool_calls, function_calls, input_tokens, output_tokens = agent_base.call(
                                    message_record.get_msgs(), temp=temperature)
                                print(res)
                                print_and_log("analyse result:\n" + res_content)
                                update_tokens(input_tokens, output_tokens)
                                bug_update_tokens(input_tokens, output_tokens)
                                message_record.add_assistant_msg(res_content, [])


                if bug_locations_extracted == True or (not location_extraction_flag):
                    # Advanced location identification
                    if advanced_identification:
                        message_record.add_msg("user", location_double_ask_force)
                        retry = 0
                        while retry < 3:
                            res, res_content, raw_tool_calls, function_calls, input_tokens, output_tokens = agent_base.call(
                                message_record.get_msgs(), response_format="json_object", max_tokens=1024, temp=temperature)

                            update_tokens(input_tokens, output_tokens)
                            bug_update_tokens(input_tokens, output_tokens)
                            print_and_log("prompt:\n" + message_record.get_last_msg()["content"])
                            print_and_log("response for more locations:")
                            print_and_log(res_content)
                            flag, res_dict = extract_json_from_response(res_content)
                            if flag == 0:
                                retry += 1
                                continue

                            more_bug_locations = res_dict.get("more_suspicious_locations")

                            if more_bug_locations:
                                message_record.add_assistant_msg(res_content, [])

                                print_and_log("============= More Suspicious Locations Extraction =============")
                                more_location_extractions = []
                                more_location_extraction_list = []
                                repair_advice_list = []
                                for bug_loc in more_bug_locations:
                                    print_and_log("more_bug_loc:\n")
                                    print_and_log(bug_loc)

                                    if isinstance(bug_loc, dict):

                                        bug_repair_advice = bug_loc.get("repair_advice")
                                        bug_file = bug_loc.get("file")
                                        bug_file = bug_file.strip()
                                        bug_class = bug_loc.get("class")
                                        bug_class = bug_class.strip().split("$")[-1].split(".")[-1]
                                        bug_method = bug_loc.get("method")
                                        bug_method = bug_method.strip()
                                        bug_method = detect_constructor(bug_method, bug_class)
                                        bug_file, bug_class, bug_method, output, candidate_list = get_bl_output(
                                            bug_file, bug_class, bug_method, bug_codebase, tools_collect,
                                            codebase_path, proj_test_pattern_begin)

                                        more_location_extractions.append(output)
                                        if not candidate_list:
                                            print_and_log("No candidates.")
                                            more_location_extraction_list.append([])
                                        else:
                                            more_location_extraction_list.append(candidate_list.copy())

                                        repair_advice_list.append(bug_repair_advice)

                                    else:
                                        print_and_log("This bug_loc is not a dict!!!!!")

                                more_locations = []
                                print_and_log("more_location_extraction_list:")
                                print_and_log(more_location_extraction_list)

                                for i,loc in enumerate(more_location_extraction_list):
                                    advice = repair_advice_list[i]
                                    if not loc:
                                        continue
                                    if len(loc) > 1:
                                        print_and_log("More than one candidate:")
                                        print_and_log(loc)
                                    for item in loc:
                                        item_dict = {"comment": item["comment"], "code": item["code"],
                                                     "start_line": item["start_line"], "end_line": item["end_line"],
                                                     "file": item["file"], "class": item["parent_name"],
                                                     "method": item["method"], "signature": item["signature"],"repair_advice":advice}
                                        more_locations.append(item_dict)
                                if more_locations:
                                    # bug_locations.extend(more_locations)
                                    for element in more_locations:
                                        if not check_exist(element,bug_locations):
                                            bug_locations.append(element)

                                    bug_locations = remove_duplicate(bug_locations)
                                    message_record.add_msg("user", construct_buggy_loc(bug_locations) + sort_buggy_methods)


                                else:
                                    print_and_log("No more buggy locations.")
                                    bug_locations = remove_duplicate(bug_locations)
                                    message_record.remove_last_msg()
                                    if recheck_conduct:
                                        message_record.remove_last_msg()
                                        message_record.remove_last_msg()
                                    else:
                                        message_record.remove_last_msg()

                                    message_record.add_msg("user", construct_buggy_loc(bug_locations) + sort_buggy_methods)

                            # The agent considers there to be no more buggy locations
                            else:
                                message_record.remove_last_msg()
                                if recheck_conduct:
                                    message_record.remove_last_msg()
                                    message_record.remove_last_msg()
                                else:
                                    message_record.remove_last_msg()
                                message_record.add_msg("user", construct_buggy_loc(bug_locations) + sort_buggy_methods)

                            break

                    else:
                        if recheck_conduct:
                            message_record.remove_last_msg()
                            message_record.remove_last_msg()
                        else:
                            message_record.remove_last_msg()

                        message_record.add_msg("user",construct_buggy_loc(bug_locations) + sort_buggy_methods)

                    # Only one candidate exists, ranking is not necessary
                    if len(bug_locations) == 1:
                        top_1_buggy = bug_locations[0]
                        #  TODO: The prompt should be removed
                        with open(os.path.join(bug_output_dir, f'{bug_id}.json'), 'w') as file:
                            json.dump(bug_locations, file, indent=4)
                        with open(os.path.join(bug_output_dir, "root_cause.txt"), 'w') as file:
                            file.write(root_cause)
                        bug_location = bug_locations[0]
                        bug_location["level"] = 1
                        bug_location_list = [bug_location]
                        with open(os.path.join(bug_output_dir, "sorted_methods.json"), 'w') as file:
                            json.dump(bug_location_list, file, indent=4)

                    # Skipping location extraction validation results in no locations extracted, and `advanced location identification` does not identify any locations either.
                    elif len(bug_locations) == 0:
                        top_1_buggy = {}
                        with open(os.path.join(bug_output_dir, f'{bug_id}.json'), 'w') as file:
                            json.dump(bug_locations, file, indent=4)
                        with open(os.path.join(bug_output_dir, "root_cause.txt"), 'w') as file:
                            file.write(root_cause)
                        with open(os.path.join(bug_output_dir, "sorted_methods.json"), 'w') as file:
                            json.dump([], file, indent=4)
                    else:
                        # Ranking
                        rtry = 0
                        while rtry < 3:
                            res, res_content, raw_tool_calls, function_calls, input_tokens, output_tokens = agent_base.call(
                                message_record.get_msgs(), response_format="json_object", max_tokens=1024, temp=temperature)
                            update_tokens(input_tokens, output_tokens)
                            bug_update_tokens(input_tokens, output_tokens)
                            print_and_log("prompt:\n" + message_record.get_last_msg()["content"])
                            print_and_log("rank:")
                            print_and_log(res_content)
                            flag, res_dict = extract_json_from_response(res_content)
                            if flag == 0:
                                rtry += 1
                                continue

                            with open(os.path.join(bug_output_dir, f'{bug_id}.json'), 'w') as file:
                                json.dump(bug_locations, file, indent=4)
                            with open(os.path.join(bug_output_dir, "root_cause.txt"), 'w') as file:
                                file.write(root_cause)

                            sorted_methods = extract_sorted_methods(bug_locations, res_dict)
                            if sorted_methods:
                                top_1_buggy = sorted_methods[0]

                            message_record.add_assistant_msg(res_content, [])
                            break

                extracted_methods = bug_codebase.get_extracted_methods_list()
                with open(os.path.join(bug_output_dir, "extracted_methods.json"), "w") as f:
                    f.write(json.dumps(extracted_methods, indent=4))
                raise TaskMainNormalExit(f"Normal exit for {bug_id}\n")
        else:
            print_and_log("The FL agent doesn't call any tools at the beginning.")
            raise TaskMainErrorExit(
                f"Error exit for {bug_id}: The FL agent doesn't call any tools at the beginning.\n")
            # sys.exit(1)
    finally:
        conversation_log = Path(bug_output_dir, f"conversation.json")
        conversation_log.write_text(json.dumps(message_record.get_msgs(), indent=4))
        func_call_record_all_log = Path(bug_output_dir, f"tool_invocation_record.json")
        func_call_record_all_log.write_text(json.dumps(func_call_record_all, indent=4))
        time_end = time.time()
        time_cost = time_end - time_start
        print_and_log(f"Time cost: {time_cost} seconds.")
        with open(os.path.join(bug_output_dir, "time_cost"), "w") as f:
            f.write(f"{time_cost}")

        top_1 = Path(bug_output_dir, "top-1.json")
        top_1.write_text(json.dumps(top_1_buggy, indent=4))

        sorted_methods_file = Path(bug_output_dir, "sorted_methods.json")
        if sorted_methods:
            sorted_methods_file.write_text(json.dumps(sorted_methods, indent=4))

        logger.remove(log_handler_id)



