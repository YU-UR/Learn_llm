from langchain_community.document_loaders import UnstructuredMarkdownLoader
from langchain_core.messages import SystemMessage, HumanMessage

from langchain_text_splitters import RecursiveCharacterTextSplitter
from mcp.server.fastmcp.prompts.base import UserMessage
from openai import OpenAI
from pymilvus import MilvusClient,DataType
from langchain_openai import ChatOpenAI


class SyncEmbedding:
    def __init__(self, collection_name, chunk_size=500, chunk_overlap=100,
                 embed_api_key="sk- ",
                 embed_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                 api_key="sk- ",
                 base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                 milvus_host="localhost:19530",
                 ):
        self.splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap, length_function=len)

        self.embed_client = OpenAI(api_key=embed_api_key, base_url=embed_base_url)
        self.llm = ChatOpenAI(api_key=api_key, base_url=base_url, model="deepseek-v3")
        self.milvus_client = MilvusClient(uri=milvus_host)
        self.collection_name = collection_name

    def embedding(self, query):
        completion = self.embed_client.embeddings.create(
            model="text-embedding-v4",
            input=query,
            dimensions=1024,
            encoding_format="float"
        )
        return completion.data[0].embedding

    def insert_vector(self, file_path):
        loader = UnstructuredMarkdownLoader(file_path)
        contents = loader.load()
        doc_result = self.splitter.split_documents(contents)
        data_list = []
        count = 1
        for doc in doc_result:
            print(doc.page_content)
            vector = self.embedding(doc.page_content)
            data = {"id": count, "dense_vector": vector, "text": doc.page_content}
            count += 1
            data_list.append(data)
        self.milvus_client.create_collection(collection_name=self.collection_name, data=data_list)
        return True

    def search_vector(self, query):
        query_vector = [self.embedding(query)]
        res = self.milvus_client.search(collection_name=self.collection_name, data=query_vector, limit=3, output_fields=["text"])
        return res

    def answer_qestion(self, query):
        answer_data = self.search_vector(query)
        total_answer = ""
        for answer in answer_data[0]:
            # text = answer.text
            # answer = self.client.chat(messages=[{"role": "user", "content": text}])
            print(answer["entity"]["text"])
            total_answer += answer["entity"]["text"]+"\n"

        messages = [SystemMessage(content=f"你是一位智能助手，你只能基于以下的检索信息进行回答。\n 检索信息:\n{total_answer}"), HumanMessage(content=query)]

        answer_res = self.llm.invoke(messages=messages)
        return answer_res


if __name__ == '__main__':
    embedding = SyncEmbedding(collection_name="test_collection")
    embedding.insert_vector("D:/Workspace/pycharm-work/learn_llm/milvus/wenjie.md")
    res = embedding.search_vector("问界M8怎么样？")
    print(res)