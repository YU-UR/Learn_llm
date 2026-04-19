import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict

from mcp.server.fastmcp import FastMCP

server = FastMCP("mcp_server", port=8080, host="0.0.0.0")


# tool封装

@server.tool(description="计算两个数字的和，需要传入两个数，并返回两个数的和", name="add")
async def add_func(a: int, b: int) -> int:
    print("add_func")
    return a + b


@server.tool(description="计算两个数字的差，需要传入两个数，并返回两个数的差", name="sub")
async def sub_func(a: int, b: int) -> int:
    print("sub_func")
    return a - b


@server.tool(description="获取当前时间", name="current_time")
async def get_current_time() -> str:
    print("get_current_time")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return now


# 静态文本资源
@server.resource("config://app_settings")
def get_app_config() -> dict[str, str]:
    print("get_app_config")
    return {
        "app_name": "mcp_server",
        "app_version": "1.0.0",
        "app_description": "mcp_server is a mcp server",
        "language": "zh-CN"
    }


# 动态生成资源
@server.resource("system://server_time")
def get_server_time() -> str:
    print("get_server_time")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return now


# 文件系统资源(绝对路径)
@server.resource("file:///Users/yhy/work/learn_llm/{path}", description="获取文件指定内容", name="read_file")
async def read_file(path: str) -> dict[str, str]:
    print("read_file")
    file_path = Path(f"/Users/yhy/work/learn_llm/{path}")
    if not file_path.exists():
        return {"error": "file not found"}

    try:
        if file_path.suffix in [".txt", ".md", ".html", ".css", ".js", ".ts", ".py", ".java", ".c", ".cpp", ".h", ".go", ".sh", ".bash",]:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                return {"content": content}
        else:
            return {"error": "file type not supported"}
    except Exception as e:
        return {"error": f" Read failed: {str(e)}"}


# MCP访问prompt
@server.prompt(description="这是一个智能客服提示模板", name="assistant")
async def assistant_customer(language: str = "English"):
    language_mcp = {
        "English": "English",
        "German": "German",
        "Chinese": "Chinese"
    }

    prompt_template = """
    # 角色
    你是一位专业的架构师，你的名字叫UU，你具备10年多的架构师经验
    # 功能
    - 你主要用{language_mcp[language]}语言来回答问题
    
    """
    return prompt_template


if __name__ == '__main__':
    server.run(transport="sse")
