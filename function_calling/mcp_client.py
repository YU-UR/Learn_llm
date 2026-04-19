import asyncio
import os

from mcp import ClientSession
from mcp.client.sse import sse_client


async def async_client():
    async with sse_client("http://127.0.0.1:8080/sse") as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            print("mcp_server 建联成功")

            print("\n 获取tool列表:")
            tool_response = await session.list_tools()
            for tool in tool_response.tools:
                print(f" -{tool.name}:{tool.description}")

            print("\n 获取resource列表:")
            resource_response = await session.list_resources()
            print("可用资源：")
            for resource in resource_response.resources:
                print(f" -{resource.uri}:{resource.description}")

            print("\n 获取prompt列表:")
            prompt_response = await session.list_prompts()
            print("可用prompt：")
            for prompt in prompt_response.prompts:
                print(f" -{prompt.name}:{prompt.description}")

            # 测试调用 tool
            print("\n 测试调用tool:")
            try:
                res = await session.call_tool("add", {"a": 1, "b": 2})
                print(f"1+1={res.content}")
            except Exception as e:
                print(f"tool failed:{e}")

            # 测试读取文件资源
            print("\n 测试读取资源:")
            # file_path = os.path.join(os.path.dirname(__file__), "test.txt")
            try:
                res = await session.read_resource(uri="file:///root/mcp_server.py")
                if res.content:
                    content = res.contents[0]
                    if hasattr(content, 'text'):
                        print(content.text)
                        # print(f" 资源读取成功，内容长度为{len(content.text)}字符")
                        # print("前100个字符：")
                        # print(content.text[:100])
                    else:
                        print(f" 读取资源成功:{content}")
                else:
                    print("资源内容为空")
            except Exception as e:
                print(f"资源读取失败:{e}")


if __name__ == '__main__':
    asyncio.run(async_client())
