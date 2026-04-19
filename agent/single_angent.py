import asyncio
from typing import Type, Any

from langchain_core.tools import BaseTool
from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

llm = ChatOpenAI(
    api_key="sk- ",  # 阿里百炼
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    model="deepseek-v3",
)


class AddArgs(BaseModel):
    a: int = Field(..., description="The first add number")
    b: int = Field(..., description="The second add number")


class AddTool(BaseTool):
    name: str = "Add"
    description: str = "Add two numbers"
    args_schema: Type[BaseModel] = AddArgs

    def _run(self, a: int, b: int):
        print("同步调加法方法...")
        return a + b

    async def _arun(self, a: int, b: int):
        print("异步调用加法...")
        return a + b


class SubArgs(BaseModel):
    a: int = Field(..., description="The first sub number")
    b: int = Field(..., description="The second sub number")


class SubTool(BaseTool):
    name: str = "Sub"
    description: str = "Sub two numbers"
    args_schema: Type[BaseModel] = SubArgs

    def _run(self, a: int, b: int):
        print("同步调减法方法...")
        return a - b

    async def _arun(self, a: int, b: int):
        print("异步调用加法...")
        return a - b


agent = create_react_agent(model=llm, tools=[AddTool(), SubTool()])

# 同步调用
# res = agent.invoke({"messages": ["请帮我计算一下2+3-5等于多少"]})
# print(res)


# 异步调用
async def main():
    res = await agent.ainvoke({"messages": ["请帮我计算一下2+3-5等于多少"]})
    print(res)


if __name__ == "__main__":
    asyncio.run(main())
