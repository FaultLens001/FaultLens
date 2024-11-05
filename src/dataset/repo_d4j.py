import subprocess
import os
import sys
from config.constants import JAVA_HOME

script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(script_dir)
COMMON_SOURCE_DIRS_PATTERN = [
    ("src/main/java/", "src/test/java/"),
    ("source/", "tests/"),
    ("src/java/", "src/test/"),
    ("gson/src/main/java/", "gson/src/test/java/"),
    ("src/", "test/")

]

errors_upbound = 5


def initialize_repo(project,bug_id,codebase_path):
    new_env = os.environ.copy()
    new_env['JAVA_HOME'] = JAVA_HOME
    res = subprocess.run(["defects4j","checkout","-p",project,"-v",bug_id+"b","-w",codebase_path],stdout=subprocess.PIPE, stderr=subprocess.PIPE,env=new_env, text=True)


def recognize_pattern(root_dir):
    main_src = None
    test_src = None
    mp = None
    tp = None
    for main_pattern, test_pattern in COMMON_SOURCE_DIRS_PATTERN:
        potential_main_src = os.path.join(root_dir, main_pattern)
        potential_test_src = os.path.join(root_dir, test_pattern)
        if os.path.isdir(potential_main_src):
            main_src = potential_main_src
        if os.path.isdir(potential_test_src):
            test_src = potential_test_src
        if main_src and test_src:
            mp = main_pattern
            tp = test_pattern
            break
    return mp, tp
