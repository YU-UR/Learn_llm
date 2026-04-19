import asyncio
from openai import OpenAI

from pymilvus import AsyncMilvusClient, DataType
from langchain_community.document_loaders import Docx2txtLoader
from langchain_text_splitters import CharacterTextSplitter

client = OpenAI(
    api_key="sk- ",  # 阿里百炼
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
)


async def embedding(query):
    completion = client.embeddings.create(
        model="text-embedding-v4",
        input=query,
        dimensions=1024,
        encoding_format="float"
    )
    return completion.data[0].embedding


class AsyncMilvusOperator:

    def __init__(self):
        self.client = AsyncMilvusClient(uri="http://localhost:19530", db_name="default")

    async def create_schema(self):
        schema = self.client.create_schema(auto_id=True, description="向量数据库的参数模型")
        schema.add_field(field_name="id", datatype=DataType.INT64, is_primary=True, description="主键")
        schema.add_field(field_name="dense_vector", datatype=DataType.FLOAT_VECTOR, dim=1024, description="密集向量")
        schema.add_field(field_name="text", datatype=DataType.VARCHAR, max_length=4096, description="文本内容")
        return schema

    async def create_collection(self):
        await self.client.create_collection(collection_name="test_collection", schema=await self.create_schema(),
                                            description="数据表操作demo")
        index_params = self.client.prepare_index_params()
        index_params.add_index(field_name="dense_vector", index_type="FLAT", metric_type="COSINE")
        await self.client.create_index(collection_name="test_collection", index_params=index_params)

    async def insert_vector(self, data):
        res = await self.client.insert(collection_name="test_collection", data=data)
        return res

    async def search_vector(self, query_vector):
        res = await self.client.search(collection_name="test_collection", data=query_vector, limit=3,
                                       output_fields=["text"])
        return res


async def main():
    # doc_loader = Docx2txtLoader("D:/Workspace/pycharm-work/learn_llm/milvus/wenjie.docx")
    # content = doc_loader.load()
    # splitter = CharacterTextSplitter(chunk_size=500, chunk_overlap=100, separator="", length_function=len)
    # contents = splitter.split_documents(content)
    # data_list = []
    # for doc in contents:
    #     print(doc.page_content)
    #     vector = await  embedding(doc.page_content)
    #     data_list.append({"dense_vector": vector, "text": doc.page_content})
    query = "问界M8怎么样？"
    query_vector = [await embedding(query)]
    milvus_operator = AsyncMilvusOperator()
    # await milvus_operator.create_collection()
    # await milvus_operator.insert_vector(data_list)
    res = await milvus_operator.search_vector(query_vector)
    print(res)


if __name__ == '__main__':
    asyncio.run(main())
