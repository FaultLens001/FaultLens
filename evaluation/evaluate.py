import argparse
import json
import os

ground_truth_file = "data/meta/Defects4J-v-1-2.json"
failed_test_dir = "data/covered_failing_test"


def check_match(method, meta_info):
    # For bugs that lack method-level ground truth
    if "functions" not in meta_info:
        return False
    functions = meta_info["functions"]
    ground_truth = []
    for func in functions:
        ground_truth.append({"path": func["path"], "end_loc": func["end_loc"]})

    for g in ground_truth:
        loc = g["path"]
        end = g["end_loc"]
        if (method['file'] == loc) and (method['end_line'] == end):
                return True

    return False

def checkexists(file,start,end,agg_methods_list):
    for method in agg_methods_list:
        if method["file"] == file and method["start_line"] == start and method["end_line"] == end:
            return method
    return None


def find_method(covered_failed_test_info, method_file, method_end):
    for element in covered_failed_test_info:
        if element["file"] == method_file and element["end_line"] == method_end:
            return element["failing_tests_count"]

    print("Cannot happen")
    exit(1)



if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Configure output directory and validation")
    parser.add_argument("-d", "--FL_directory", type=str, required=True, help="Directory for FL results")
    parser.add_argument("-v","--validation", type=int, default=1, help="Whether use location extraction validation(1:use 0:not use)")
    parser.add_argument("-o", "--output_file", type=str, default="result.json", help="Output file for evaluation results")
    args = parser.parse_args()
    with open(ground_truth_file,"r") as f:
        ground_truth = json.load(f)

    run_dirlist = os.listdir(args.FL_directory)


    evaluate_bugs = {}
    for bug in ground_truth:

        agg_methods_list = []
        r_bug_dir = []
        for run_dir in run_dirlist:
            complete_run_dir = os.path.join(args.FL_directory,run_dir,bug)
            if not os.path.isdir(complete_run_dir):
                continue
            subfolders = [f for f in os.listdir(complete_run_dir) if os.path.isdir(os.path.join(complete_run_dir, f))]
            max_subfolder = max(subfolders, key=lambda x: int(x)) if subfolders else None

            r_bug_dir.append(os.path.join(args.FL_directory,run_dir,bug,max_subfolder))

        max_methods_length = 0
        for bug_dir in r_bug_dir:

            sorted_methods_file = os.path.join(bug_dir, "sorted_methods.json")
            methods_file = os.path.join(bug_dir,f"{bug}.json")
            if not os.path.exists(methods_file):
                # print(f"{bug} {bug_dir} {bug}.json not exists!")
                continue
            if not os.path.exists(sorted_methods_file):
                # Such case: the invocation loop has reached the maximum number of rounds while the agent rechecks
                # and denies all the identified locations.
                # print(f"{bug} {bug_dir} sorted_methods.json not exists!")
                continue
                # exit(0)

            with open(sorted_methods_file, 'r') as f:
                sorted_methods = json.load(f)

            if not sorted_methods:
                if args.validation == 0:
                    continue
                print(f"{bug} {bug_dir} sorted_methods.json is empty! Please check the FL output.")

                exit(0)


            with open(methods_file, 'r') as f:
                methods = json.load(f)


            if len(sorted_methods) != len(methods):
                print(f"The number of methods in {bug} {bug_dir} sorted_methods.json not equal to {bug}.json! Please check the FL output.")
                exit(0)
            if len(sorted_methods) > max_methods_length:
                max_methods_length = len(sorted_methods)

        evaluate_bugs[bug] = {}
        evaluate_bugs[bug]["max_methods_list_length"] = max_methods_length


        for run_dir in run_dirlist:
            # print(run_dir)
            run_dir_path = os.path.join(args.FL_directory,run_dir,bug)
            if not os.path.isdir(run_dir_path):
                continue
            subfolders = [f for f in os.listdir(run_dir_path) if os.path.isdir(os.path.join(run_dir_path, f))]
            meta_info = ground_truth[bug]
            project = bug.split("-")[0]
            id = bug.split("-")[1]
            max_subfolder = max(subfolders, key=lambda x: int(x)) if subfolders else None
            bug_dir = os.path.join(run_dir_path,max_subfolder)
            json_file_path = os.path.join(bug_dir, f"{bug}.json")
            sorted_methods_path = os.path.join(bug_dir, "sorted_methods.json")
            time_cost_path = os.path.join(bug_dir, "time_cost")
            time_cost = -1
            ranked = True
            candidate_methods = []
            if os.path.exists(time_cost_path):
                with open(time_cost_path, 'r') as f:
                    time_cost = float(f.read().strip())

            evaluate_bugs[bug][run_dir] = {}
            evaluate_bugs[bug][run_dir]["time_cost"] = time_cost
            match_number = 0
            if not os.path.exists(json_file_path):
                evaluate_bugs[bug][run_dir]["sorted_methods"] = []
                continue

            else:
                if not os.path.exists(sorted_methods_path):
                    continue
                with open(sorted_methods_path, 'r') as f:
                    sorted_bug_infos = json.load(f)

                if not sorted_bug_infos:
                    evaluate_bugs[bug][run_dir]["sorted_methods"] = []
                    # print(run_dir + bug + ":sorted_methods.json is empty!\n")
                    continue

                simplified_sorted_methods = []
                for method in sorted_bug_infos:
                    simplified_sorted_methods.append({"file":method["file"],"start_line":method["start_line"],"end_line":method["end_line"]})
                evaluate_bugs[bug][run_dir]["sorted_methods"] = simplified_sorted_methods


                max_score = evaluate_bugs[bug]["max_methods_list_length"]
                for method in sorted_bug_infos:
                    score = max_score - sorted_bug_infos.index(method)
                    method_file = method["file"]
                    method_start = method["start_line"]
                    method_end = method["end_line"]
                    target_method = checkexists(method_file,method_start,method_end,agg_methods_list)
                    if "functions" not in meta_info:
                        # print(f"{bug} has no ground truth!")
                        failed_test_count = 0

                    else:
                        with open(os.path.join(failed_test_dir,bug+".json"),"r")as f:
                            covered_failed_test_info = json.load(f)

                        failed_test_count = find_method(covered_failed_test_info,method_file,method_end)


                    if target_method is not None:
                        target_method["score"] += score
                        target_method["score_list"].append(score)
                    else:
                        agg_methods_list.append({"file":method_file,"start_line":method_start,"end_line":method_end,"score":score,"score_list":[score],"failed_test_count": failed_test_count})


        evaluate_bugs[bug]["aggregate_methods_list"] = agg_methods_list



    for bug in evaluate_bugs:
        final_methods_list = evaluate_bugs[bug]["aggregate_methods_list"]
        final_methods_list.sort(key=lambda x: (-x['score'], -x['failed_test_count']))

        match_number = 99999
        for i,method in enumerate(final_methods_list):
            if (check_match(method,ground_truth[bug])):
                match_number = i + 1
                break
        evaluate_bugs[bug]["top_n"] = match_number

    # print top-n
    top_1 = []
    top_3 = []
    top_5 = []
    bug_count = 0
    for bug in evaluate_bugs:
        bug_count += 1
        if evaluate_bugs[bug]["top_n"] == 1:
            top_1.append(bug)
        if evaluate_bugs[bug]["top_n"] <= 3:
            top_3.append(bug)
        if evaluate_bugs[bug]["top_n"] <= 5:
            top_5.append(bug)
    # print("bug num:",bug_count)

    print(f"Top-1: {len(top_1)}")
    print(f"Top-3: {len(top_3)}")
    print(f"Top-5: {len(top_5)}")

    with open(args.output_file, "w") as f:
        json.dump(evaluate_bugs,f,indent=4)









