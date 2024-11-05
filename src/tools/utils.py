import os
import re
from typing import List
from loguru import logger
from openai.types.chat import ChatCompletionMessageToolCall


COMMON_SOURCE_DIRS = [
    ("src/main/java", "src/test/java"),
    ("source", "tests"),
    ("src/java", "src/test"),
    ("gson/src/main/java", "gson/src/test/java"),
    ("src","test")

]


def inspect_tools(raw_tool_calls: List[ChatCompletionMessageToolCall]) -> List[ChatCompletionMessageToolCall]:
    tool_calls = []
    for tool_call in raw_tool_calls:
        called_func = tool_call.function
        func_name = called_func.name

        if validate_function_name(func_name):
            tool_calls.append(tool_call)
        # else:
        #     print_and_log(f"Invalid function name: {func_name}")
    return tool_calls


def remove_newlines(input_str):
    return input_str.replace("\n", " ").replace("\r", " ")


def validate_function_name(name):
    pattern = r'^[a-zA-Z0-9_-]+$'
    if re.match(pattern, name):
        return True
    else:
        return False


def remove_modifiers_and_return_type(input_str):
    modifier_pattern = re.compile(r'^(public|protected|private|static|final|abstract|synchronized|transient|volatile|native|strictfp)?\s*(\w+)?\s+(\w+\s*\([^)]*\))$')
    match = modifier_pattern.match(input_str)
    if match:
        return match.group(3)
    return input_str

def process_method_input(input_str):
    """Preprocessing for extract_method."""
    input_str = input_str.strip()
    cleaned_input = remove_modifiers_and_return_type(input_str)
    pure_name_pattern = re.compile(r'^\w+$')
    signature_pattern = re.compile(r'^(\w+)\s*\(([^)]*)\)$')
    if pure_name_pattern.match(cleaned_input):
        return {"name": cleaned_input, "type": "name"}

    match = signature_pattern.match(cleaned_input)
    if match:
        method_name = match.group(1)
        return {
            "name": method_name,
            "signature": cleaned_input,
            "type": "name+signature"
        }

    return None


def extract_param_types(parameters):
    param_list = [param.strip() for param in parameters.split(',')]

    param_types = []
    for param in param_list:
        type_match = re.match(r'^(\w+(\s*\[\s*\])*)\s*\w*$', param)
        if type_match:
            param_types.append(type_match.group(1))

    return param_types


def extract_method_name(method_name):
    pattern = re.compile(r'^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\(')
    match = pattern.match(method_name)
    if match:
        return match.group(1)
    else:
        return method_name


def split_methods(input_string):
    pattern = re.compile(r'(\(\d+\)\s*<file>.*?</file>.*?)(?=\(\d+\)\s*<file>|$)', re.DOTALL)
    methods = pattern.findall(input_string)

    return methods



