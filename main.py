import argparse
import os
import shutil
import tempfile
import time
from itertools import islice
from loguru import logger
import json

from config.constants import codebase_base
from src.custom_signal import TaskMainNormalExit, TaskMainErrorExit
from src.dataset.repo_d4j import initialize_repo
from src.task import run
import concurrent.futures
fail_bug_list = []


def create_temp_directory():
    if not os.path.exists("tmp"):
        os.makedirs("tmp")
    temp_dir = tempfile.mkdtemp(dir="tmp")
    return temp_dir


def delete_temp_directory(temp_dir):
    shutil.rmtree(temp_dir)


def task_main(r, temperature, model_type, bug,bug_info,codebase_path,try_count,output_dir):

    bug_output = os.path.join(output_dir, bug, str(try_count))
    if os.path.exists(bug_output):
        raise TaskMainNormalExit(f"Directory {bug_output} already exists. Exiting. Normal exit for {bug}\n")
        # sys.exit(0)
    else:
        os.makedirs(bug_output, exist_ok=True)

    first_trigger_test = list(bug_info['trigger_test'].keys())[0]
    trigger_test_src = bug_info["trigger_test"][first_trigger_test]["src"]
    trigger_test_path = bug_info["trigger_test"][first_trigger_test]["path"]
    clean_error_info = bug_info["trigger_test"][first_trigger_test]["clean_error_msg"]
    trigger_test_info = {"src":trigger_test_src,"path":trigger_test_path,"clean_error_info":clean_error_info}
    parsed_dir = os.path.join(os.path.dirname(codebase_path), "parsed")
    # location_extraction_flag: Indicates whether location extraction validation is enabled (default=True).
    # If set to False, use -v 0 when running evaluate.py, as evaluation steps differ slightly.
    run(parsed_dir, r, temperature, model_type, bug, str(bug_output), trigger_test_info, codebase_path, trigger_test=first_trigger_test,
        advanced_identification=True, re_check=True, partial_save=True, issue_analysis=True, review_result=True, location_extraction_flag=True)


def main(meta_path, agent_number, model_type, temperature, r, output_dir):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    with open(meta_path,"r") as f:
        data = json.load(f)
    for n in range(1,agent_number+1):
        output = os.path.join(output_dir, f"agent_{n}")
        for bug, bug_info in islice(data.items(),0, None):
            temp_dir = create_temp_directory()
            if bug not in ["Closure-63", "Closure-93", "Lang-2", "Time-21"]:
                codebase_path = os.path.join(temp_dir, bug)
            else:
                codebase_path = os.path.join(codebase_base, bug)

            initialize_repo(bug.split("-")[0],bug.split("-")[1],codebase_path)


            try_count = 0

            while try_count < 3:

                try:
                    task_main(r-1, temperature, model_type, bug, bug_info, codebase_path, try_count, output)
                    # print(f"agent_{n}: Finish {bug}")
                    break

                except TaskMainNormalExit as e:
                    print(e)
                    delete_temp_directory(temp_dir)
                    break
                except TaskMainErrorExit as e:
                    print(e)
                    error_info = f"Error in {bug} : {e}"
                    with open(os.path.join(output_dir, "fail_bug_list.txt"), "a+") as f:
                        f.write(f"agent_{n}:" + error_info + "\n")
                    delete_temp_directory(temp_dir)
                    break

                except Exception as e:
                    print(e)
                    if (("Connection error" in str(e)) or ("Request timed out" in str(e)) or ("request contained invalid JSON: Expecting value:" in str(e))) and try_count < 3:
                        time.sleep(30)
                        with open(os.path.join(output_dir, "fail_bug_list.txt"), "a+") as f:
                            f.write(f"agent_{n}: Retry {bug}: {e}\n")
                        try_count += 1
                        if try_count == 3:
                            delete_temp_directory(temp_dir)

                        continue
                    else:

                        bug_info = f"Error in {bug} : {e}"
                        with open(os.path.join(output_dir, "fail_bug_list.txt"), "a+") as f:
                            f.write(f"agent_{n}:" + bug_info + "\n")
                        delete_temp_directory(temp_dir)
                        break
            time.sleep(5)


if __name__ == "__main__":
    logger.remove()
    parser = argparse.ArgumentParser(description="Configure agent count, model type, temperature, and round limit")
    parser.add_argument("-n", "--agent_number", type=int, default=1, help="Number of agents (default is 1)")
    parser.add_argument("-m", "--model_type", type=str, default="gpt-4o-mini", help="Specific model type (default is gpt-4o-mini)")
    parser.add_argument("-t", "--temperature", type=float, default=0.2, help="Model temperature (default is 0.2)")
    parser.add_argument("-l", "--upper_limit", type=int, default=10, help="Upper limit for tool invocation (default is 10)")
    parser.add_argument("-o", "--output_dir", type=str, required=True, help="Output directory for results")
    args = parser.parse_args()
    meta_path = "data/meta/Defects4J-v-1-2.json"

    main(meta_path, args.agent_number, args.model_type, args.temperature, args.upper_limit, args.output_dir)




