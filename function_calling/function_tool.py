from datetime import datetime, timedelta

from langchain_core.tools import tool
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
from langchain_openai import ChatOpenAI

"""
加@装饰器之后，可以获取函数内部信息，如computing_time.args/description/name
"""


@tool
def get_current_time():
    """获取当前时间"""
    current_time = datetime.now()
    return current_time.strftime("%Y-%m-%d %H:%M:%S")


@tool
def computing_time(current_time, minutes):
    """计算时间"""
    new_time = datetime.strptime(current_time, "%Y-%m-%d %H:%M:%S") + timedelta(minutes=minutes)
    return new_time.strftime("%Y-%m-%d %H:%M:%S")


# 映射
tool_map = {
    "get_current_time": get_current_time,
    "computing_time": computing_time
}

llm = ChatOpenAI(
    api_key="sk- ",  # 阿里百炼
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    model="deepseek-v3"
)
with_tool_llm = llm.bind_tools([get_current_time, computing_time])

messages = [
    SystemMessage(
        content="你是一个专业时间记录者，你支持获取当前时间的功能，并且可以根据当前时间往前往后推算时间，你必须调用工具进行回答且输出完整的时间，包含年月日时分秒。"),
    HumanMessage(content="请告诉我现在几点钟，十分钟后是几点？")
]

while True:
    res = with_tool_llm.invoke(messages)
    if res.tool_calls:
        messages.append(res)
        for tool_call in res.tool_calls:
            function_name = tool_call.get("name", None)
            # args = tool_call.get("args", None)
            func_result = tool_map[function_name].invoke(tool_call)
            messages.append(func_result)
    else:
        print(res.content)
        messages.append(res)
        break
print(messages)
