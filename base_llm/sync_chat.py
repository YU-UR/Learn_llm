import time

from openai import OpenAI
from prompt.prompt_learn import system_prompt

# system_prompt = "你是一个智能助手，请回答我的问题。"

client = OpenAI(
    api_key="sk- ",  # 阿里百炼
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
)


class SyncChat:
    def __init__(self):
        # self.api_key = "sk-7ebe10dc4165449f94173eb52557d871"  # deepseek api
        # self.base_url = "https://api.deepseek.com/v1"
        self.client = client
        # system_prompt = "你是一个智能助手，请回答我的问题。"

    def sync_chat(self):  # 同步返回
        res = self.client.chat.completions.create(
            model="deepseek-v3",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "你叫什么名字？"}
            ]
        )
        return res

    def sync_chat_stream(self): # 流式返回
        res = self.client.chat.completions.create(
            model="deepseek-v3",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "你叫什么名字？"}
            ],
            stream=True
        )
        return res


if __name__ == '__main__':
    start_time = time.time()
    sync_chat = SyncChat()
    res = sync_chat.sync_chat_stream()
    # print(res)

    for i in res:
        print(i)
        print(time.time() - start_time)
