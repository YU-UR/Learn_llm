import json
from openai import OpenAI
from datetime import datetime, timedelta


def get_current_time():
    current_time = datetime.now()
    return current_time.strftime("%Y-%m-%d %H:%M:%S")


def computing_time(current_time, minutes):
    new_time = datetime.strptime(current_time, "%Y-%m-%d %H:%M:%S") + timedelta(minutes=minutes)
    return new_time.strftime("%Y-%m-%d %H:%M:%S")


client = OpenAI(
    api_key="sk- ",  # 阿里百炼
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
)
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "获取当前时间",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "computing_time",
            "description": "计算时间",
            "parameters": {
                "type": "object",
                "properties": {
                    "current_time": {
                        "type": "object",
                        "description": "当前时间"
                    },
                    "minutes": {
                        "type": "integer",
                        "description": "分钟数"
                    }
                },
                "required": ["current_time", "minutes"]
            }
        }
    }
]

tool_map = {
    "get_current_time": get_current_time,
    "computing_time": computing_time
}

messages = [
    {
        "role": "system",
        "content": "你是一个专业的时间记录者，你支持获取当前时间的功能，并且可以根据当前时间往前往后推算时间，你必须调用工具进行回答。"
    },
    {
        "role": "user",
        "content": "请告诉我现在几点钟，十分钟后是几点？"
    }
]

while True:
    res = client.chat.completions.create(
        model="deepseek-v3",
        messages=messages,
        tools=tools,
        tool_choice="auto"
    )
    if res.choices[0].message.tool_calls:
        messages.append({"role": "assistant", "content": None, "tool_calls": res.choices[0].message.tool_calls})
        for tool_call in res.choices[0].message.tool_calls:
            function_name = tool_call.function.name
            arguments = json.loads(tool_call.function.arguments)
            tool_result = tool_map[function_name](**arguments)
            messages.append({"role": "tool", "content": str(tool_result), "tool_call_id": tool_call.id})
    else:
        messages.append({"role": "assistant", "content": res.choices[0].message.content})
        break
print(messages)

#输出结果
"""
[{'role': 'system', 'content': '你是一个专业的时间记录者，你支持获取当前时间的功能，并且可以根据当前时间往前往后推算时间，你必须调用工具进行回答。'},
{'role': 'user', 'content': '请告诉我现在几点钟，十分钟后是几点？'}, 
{'role': 'assistant', 'content': None, 'tool_calls': [ChatCompletionMessageFunctionToolCall(id='call_fc24f0ab64084006abb927', function=Function(arguments='{}', name='get_current_time'), type='function', index=0)]}, 
{'role': 'tool', 'content': '2026-04-14 11:42:57', 'tool_call_id': 'call_fc24f0ab64084006abb927'}, 
{'role': 'assistant', 'content': None, 'tool_calls': [ChatCompletionMessageFunctionToolCall(id='call_5dd56a91a58345e0b1d82f', function=Function(arguments='{"current_time":"2026-04-14 11:42:57","minutes":10}', name='computing_time'), type='function', index=0)]}, 
{'role': 'tool', 'content': '2026-04-14 11:52:57', 'tool_call_id': 'call_5dd56a91a58345e0b1d82f'}, 
{'role': 'assistant', 'content': '现在是 **11:42**，十分钟后是 **11:52**。'}]
"""