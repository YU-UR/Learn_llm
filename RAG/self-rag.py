from typing import TypedDict

from langchain_community.document_loaders import UnstructuredMarkdownLoader
from langchain_core.messages import SystemMessage, HumanMessage

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langgraph.constants import START, END
from langgraph.graph import StateGraph
from mcp.server.fastmcp.prompts.base import UserMessage
from openai import OpenAI
from pymilvus import MilvusClient, DataType
from langchain_openai import ChatOpenAI

from RAG.sync_embedding import SyncEmbedding

search_obj = SyncEmbedding(collection_name="test_collection")


class RagState(TypedDict):
    input: str
    search_result: list[str]
    assistant_result: str


graph = StateGraph(RagState)


def retrieve(state):
    print("开始调检索的方法...")
    input = state["input"]
    result = search_obj.search_vector(input)
    search_reult = []
    for data in result[0]:
        search_reult.append(data["entity"]["text"])
    return {"search_result": search_reult}


def grade(state):
    print("开始调评分的方法...")
    input = state["input"]
    search_result = state["search_result"]

    check_result = []
    for result in search_result:
        system_prompt = f"你是一位数据评分员，你需要根据用户的问题和每个检索的结果进行判断，检索的结果是否与用户的问题相关，用户的问题是：{input}，检索的结果是：{result}，相关的话则只输出yes，否则输出no"
        messages = [{"role": "system", "content": system_prompt}]
        res = search_obj.llm.invoke(messages=messages)

        if "yes" in res.content:
            check_result.append(result)
    return {"search_result": check_result}


def ckeck_search_result(state):
    print("开始调检查检索结果的方法...")
    search_result = state["search_result"]
    if len(search_result) == 0:
        return "rewrite"
    return "generate"


def generate(state):
    print("开始调生成大模型结果的方法...")
    input = state["input"]
    search_result = state["search_result"]
    messages = [{"role": "system", "content": f"""用户的问题是：{input}，检索的结果：{''.join(search_result)}"""}]
    res = search_obj.llm.invoke(input=messages)
    return {"assistant_result": res.content}


def check_hallucinations(state):
    print("开始调检查 hallucinations 方法...")
    search_result = state["search_result"]
    input_answer = state["input"]
    assistant_result = state["assistant_result"]
    system_prompt = f"""你是一位数据检查员，你需要判断大模型的输出与用户的问题进行对比，检查大模型是否出现幻觉，大模型生成的结果是：{assistant_result}，检索的结果是：{''.join(search_result)}，如果没有幻觉则输出yes，有幻觉输出no"""
    messages = [{"role": "system", "content": system_prompt}]
    res = search_obj.llm.invoke(input=messages)
    if "yes" in res.content:
        return "generate"

    system_prompt = f"""你是一位数据检查员，你需要判断大模型的输出与用户的问题进行对比，判断大模型是否解决用户问题，大模型生成的结果是：{assistant_result}，用户问题是：{input_answer}，如果解决了问题则输出yes，没有解决问题则输出no"""
    messages = [{"role": "system", "content": system_prompt}]
    res = search_obj.llm.invoke(input=messages)
    if "yes" in res.content:
        return "END"
    return "rewrite"


def rewrite(state):
    print("开始调重写方法...")
    input = state["input"]
    system_prompt = f"""你是一位心理专家，你主要负责理解用户的问题，把深层含义和浅层含义理解，并形成一个新的问题，用户问题是：{input}"""
    messages = [{"role": "system", "content": system_prompt}]
    res = search_obj.llm.invoke(input=messages)
    return {"input": res.content}


graph.add_node("rewrite", rewrite)
graph.add_node("retrieve", retrieve)
graph.add_node("generate", generate)
graph.add_node("grade", grade)

graph.add_node(START, "retrieve")
graph.add_edge("retrieve", "grade")
# 条件边，没有结果使执行节点rewrite；否则执行节点 generate
graph.add_conditional_edges("grade", ckeck_search_result, {"rewrite": "rewrite", "generate": "generate"})

graph.add_node("rewrite", "retrieve")
# 条件边，有幻觉则generate ；没有幻觉但未解决问题时rewrite，否则执行节点END；
graph.add_conditional_edges("generate", check_hallucinations,
                            {"generate": "generate", "END": END, "rewrite": "rewrite"})


agent = graph.compile()

for output in agent.stream({"input": "milvus 向量数据库怎么样"}):
    print(output)
