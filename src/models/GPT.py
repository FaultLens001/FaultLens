from config.constants import OPENAI_API_KEY
from src.record import print_and_log
from openai import BadRequestError, OpenAI
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionMessageToolCall
)
from openai.types.chat.chat_completion_message_tool_call import (
    Function as OpenaiFunction,
)
import os
import sys
import json

from src.tools.utils import validate_function_name

os.environ['http_proxy'] = 'http://127.0.0.1:7890'
os.environ['https_proxy'] = 'http://127.0.0.1:7890'


def rectify_tool_calls(raw_tool_calls):
    tool_calls = []
    tool_call: ChatCompletionMessageToolCall
    for tool_call in raw_tool_calls:
        called_func: OpenaiFunction = tool_call.function
        function_name = called_func.name
        func_args_str = called_func.arguments
        if func_args_str == "":
            arguments = {}
        else:
            try:
                arguments = json.loads(func_args_str, strict=False)
            except json.decoder.JSONDecodeError:
                arguments = {}

        if function_name == "get_covered_files_from_dir":
            if (len(arguments) == 1) and ("dir_path" in arguments) and (arguments["dir_path"].endswith(".java")):
                tool_call.function.name = "get_class_info"
                class_name = arguments["dir_path"].split("/")[-1].split(".")[0]
                new_arguments = {"file_path": arguments["dir_path"], "class_name": class_name}
                called_func.arguments = json.dumps(new_arguments)
                # print_and_log("Change tool call from get_covered_files_from_dir to get_class_info.")
                # print_and_log(arguments)
        if function_name == "get_inner_class_info" and ("inner_class_name" in arguments) and (
                "class_name" in arguments):
            if ("file_path" in arguments) and (arguments["inner_class_name"] != ""):
                file_path = arguments["file_path"]
                del arguments["file_path"]
                called_func.arguments = json.dumps(arguments)
                # print_and_log(f"Remove file_path {file_path} from get_inner_class_info.")

        tool_calls.append(tool_call)

    return tool_calls


def get_clean_func_calls(tool_calls):
    if not tool_calls:
        return []

    result = []
    for call in tool_calls:
        args_dict = {}
        func_args_str = call.function.arguments
        if func_args_str:
            try:
                args_dict = json.loads(func_args_str, strict=False)
            except json.decoder.JSONDecodeError:
                pass

        if validate_function_name(call.function.name):
            result.append({"func_id": call.id, "func_name": call.function.name, "args_dict": args_dict, "called_func": call.function})

    return result


class Model:
    def __init__(self):
        self.client = None
        self.gpt_type: str = ""

    def initial_model_config(self, gpt_type: str):
        if self.client is None:
            if OPENAI_API_KEY:
                self.client = OpenAI(api_key=OPENAI_API_KEY)
            else:
                print("Please set your OPENAI_API_KEY in the ")
                sys.exit(1)

        if gpt_type in ["gpt-4o-mini", "gpt-4-turbo-2024-04-09", "gpt-4-0125-preview", "gpt-4-1106-preview",
                        "gpt-3.5-turbo-0125", "gpt-3.5-turbo-1106", "gpt-4o-2024-05-13", "gpt-4o-mini-2024-07-18",
                        "gpt-4o-2024-08-06"]:
            self.gpt_type = gpt_type
        else:
            print_and_log("The specified GPT Model is invalid.")
            sys.exit(1)

    def call(self, messages, top_p=1.0, tools=None, response_format="text", temp=0.2, max_tokens=1024):
        print_and_log(
            f"parameters of this call: model = {self.gpt_type}, temperature = {temp},top_p = {top_p}, response_format = {response_format}, max_tokens={max_tokens},\n tools={tools}\n\n")
        try:
            response: ChatCompletion = self.client.chat.completions.create(
                model=self.gpt_type,
                messages=messages,
                tools=tools,
                temperature=temp,
                response_format={"type": response_format},
                max_tokens=max_tokens,
                top_p=top_p,
                stream=False,
            )
            assert response.usage is not None
            input_tokens = int(response.usage.prompt_tokens)
            output_tokens = int(response.usage.completion_tokens)
            raw_response = response.choices[0].message
            response_dict = {}
            if response_format == "json_object":
                try:
                    response_dict = json.loads(raw_response.content)
                except (ValueError, TypeError):
                    response_dict = None

            content = raw_response.content
            if content is None:
                content = ""
            raw_tool_calls = raw_response.tool_calls
            if raw_tool_calls:
                raw_tool_calls = rectify_tool_calls(raw_tool_calls)

            func_calls = get_clean_func_calls(raw_tool_calls)

            return (
                response_dict,
                content,
                raw_tool_calls,
                func_calls,
                input_tokens,
                output_tokens
            )
        except BadRequestError as e:
            if e.code == "context_length_exceeded":
                print_and_log("Error: The context length has exceeded the allowed limit.")
            raise e
