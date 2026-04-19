import asyncio
import time

from openai import OpenAI, AsyncOpenAI


# async 需要用asyncio.run()和 await

class AsyncChat:
    def __init__(self):
        self.api_key = "sk- "
        self.base_url = "https://api.deepsek.com/v1"
        self.client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)

    async def async_chat(self):
        res = await self.client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "你是一位智能助手"},
                {"role": "user", "content": "你叫什么名字？"}
            ]
        )
        return res

    async def async_chat_stream(self):
        res = await self.client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "你是一位智能助手"},
                {"role": "user", "content": "你叫什么名字？"}
            ],
            stream=True
        )
        async for chunk in res:
            print(chunk)


if __name__ == '__main__':
    async_chat = AsyncChat()
    res = asyncio.run(async_chat.async_chat_stream())
