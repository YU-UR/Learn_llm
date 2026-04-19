import asyncio
from datetime import datetime
from typing import Type
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langgraph_supervisor import create_supervisor
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


class GetCurrentTime(BaseTool):
    name: str = "GetCurrentTime"
    description: str = "Get current time"

    def _run(self):
        print("同步调用获取当前时间方法...")
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    async def _arun(self):
        print("异步调用获取当前时间方法...")
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


math_agent = create_react_agent(model=llm, tools=[AddTool(), SubTool()],
                                prompt="""你是一位数学专家。\n
                                - 你只处理数学计算问题\n
                                - 必须通过工具完成计算\n
                                - 如果问题不是数学问题，必须拒绝，并说明应该由其他代理处理.\n
                                """,
                                name="math", debug=True)
current_agent = create_react_agent(model=llm, tools=[GetCurrentTime()],
                                   prompt="""你是一位时间专家。
                                   - 你只处理时间相关问题
                                   - 获取当前时间必须调用工具
                                   - 如果问题不是时间问题，必须拒绝
                                   """,
                                   name="current", debug=True)

supervisor = create_supervisor(model=llm, agents=[math_agent, current_agent], output_mode="full_history",
                               prompt="""
                                你是一个多代理调度器，负责协调以下代理：
                                - current：处理时间问题
                                - math：处理数学问题
                                 规则：
                                
                                1. 你必须将用户问题拆解为子任务
                                2. 每次只调用一个代理
                                3. 不允许自己直接回答
                                4. 必须明确选择一个代理执行当前任务
                                5. 当所有任务完成后，输出最终答案并停止                                
                                输出格式必须为：                               
                                {
                                  "thought": "你的思考",
                                  "next_agent": "math 或 current 或 finish",
                                  "task": "要执行的任务",
                                  "final_answer": "如果完成则填写，否则为空"
                                }
                                """
                               ).compile()
# 同步调用
res = supervisor.invoke({"messages": ["现在几点钟？"]})
print(res["message"][-1].content)


# 异步调用
async def main():
    res = await supervisor.ainvoke({"messages": ["现在几点钟，并调用工具计算一下1+2-3等于几？"]})
    print(res["message"][-1].content)


if __name__ == "__main__":
    asyncio.run(main())
