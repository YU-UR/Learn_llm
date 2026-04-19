import asyncio
import dashscope
from openai import OpenAI

from pymilvus import AsyncMilvusClient, DataType, AnnSearchRequest, RRFRanker
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


async def embedding_sparse(query):
    resp = dashscope.TextEmbedding.call(
        api_key="sk- ",
        model=dashscope.TextEmbedding.Models.text_embedding_v4,
        input=query,
        dimensions=1024,
        output_type="dense&sparse"  # 此处输出稀疏向量，而非模型提供
    )
    if resp.status_code == 200:
        sparse_vector = {item["index"]: item["value"] for item in resp.output["embeddings"][0]["sparse_embedding"]}
        dense_vector = resp.output["embeddings"][0]["embedding"]
        return dense_vector, sparse_vector
    return False


class AsyncMilvusOperator:

    def __init__(self):
        self.client = AsyncMilvusClient(uri="http://localhost:19530", db_name="default")

    async def create_schema(self):
        schema = self.client.create_schema(auto_id=True, description="向量数据库的参数模型")
        schema.add_field(field_name="id", datatype=DataType.INT64, is_primary=True, description="主键")
        schema.add_field(field_name="dense_vector", datatype=DataType.FLOAT_VECTOR, dim=1024, description="密集向量")
        schema.add_field(field_name="sparse_vector", datatype=DataType.SPARSE_FLOAT_VECTOR, description="稀疏向量")
        schema.add_field(field_name="text", datatype=DataType.VARCHAR, max_length=4096, description="文本内容")
        return schema

    async def create_collection(self):
        await self.client.create_collection(collection_name="mix_search", schema=await self.create_schema(),
                                            description="混合检索操作demo")
        index_params = self.client.prepare_index_params()
        index_params.add_index(field_name="dense_vector", index_type="FLAT", metric_type="COSINE")
        index_params.add_index(field_name="sparse_vector", index_type="SPARSE_INVERTED_INDEX", metric_type="IP")
        await self.client.create_index(collection_name="mix_search", index_params=index_params)

    async def insert_vector(self, data):
        res = await self.client.insert(collection_name="mix_search", data=data)
        return res

    async def mix_search_vector(self, dense_vector, sparse_vector):
        await self.client.load_collection(collection_name="mix_search")
        req_dense = AnnSearchRequest(
            data=[dense_vector],
            anns_field="dense_vector",
            param={"metric_type": "COSINE"},
            limit=3,
        )
        req_sparse = AnnSearchRequest(
            data=[sparse_vector],
            anns_field="sparse_vector",
            param={"metric_type": "IP"},
            limit=3,
        )
        reqs = [req_dense, req_sparse]
        ranker = RRFRanker(k=3)
        res = await self.client.hybrid_search(collection_name="mix_search", reqs=reqs, output_fields=["text"],ranker=ranker)
        return res


async def main():
    # doc_loader = Docx2txtLoader("D:/Workspace/pycharm-work/learn_llm/milvus/wenjie.docx")
    # content = doc_loader.load()
    # splitter = CharacterTextSplitter(chunk_size=500, chunk_overlap=100, separator="", length_function=len)
    # contents = splitter.split_documents(content)
    # data_list = []
    # for doc in contents:
    #     # print(doc.page_content)
    #     dense_vector, sparse_vector = await embedding_sparse(doc.page_content)
    #     print(sparse_vector)
    #     data_list.append({"dense_vector": dense_vector, "text": doc.page_content, "sparse_vector": sparse_vector})
    query = "问界M8怎么样？"
    dense_vector, sparse_vector = await embedding_sparse(query)
    milvus_operator = AsyncMilvusOperator()
    # await milvus_operator.create_collection()
    # await milvus_operator.insert_vector(data_list)
    res = await milvus_operator.mix_search_vector(dense_vector, sparse_vector)
    print(res)


if __name__ == '__main__':
    asyncio.run(main())
