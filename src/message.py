

class MessageRecord:
    def __init__(self):
        self.messages = []

    def add_msg(self, role, content):
        self.messages.append({"role": role, "content": content})

    def get_msgs(self):
        return self.messages

    def get_last_msg(self):
        return self.messages[-1]

    def remove_last_msg(self):
        self.messages.pop()

    def add_assistant_msg(self, message, tools_list):
        tool_dict_list = []
        for tool in tools_list:
            this_tool_dict = {"id": tool.id, "type": tool.type}
            func_obj = tool.function
            func_name = func_obj.name
            func_args = func_obj.arguments

            this_tool_dict["function"] = {"name": func_name, "arguments": func_args}
            tool_dict_list.append(this_tool_dict)

        if not tool_dict_list:
            self.messages.append({"role": "assistant", "content": message})
        else:
            if message:
                self.messages.append(
                    {
                        "role": "assistant",
                        "content": message,
                        "tool_calls": tool_dict_list,
                    }
                )
            else:
                self.messages.append(
                    {"role": "assistant", "content": None, "tool_calls": tool_dict_list}
                )

    def add_tool_res(self, message, tool_call_id):
        self.messages.append({"role": "tool", "content": message, "tool_call_id": tool_call_id})



