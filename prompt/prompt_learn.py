"""
system_prompt：控制模型行为；定义任务边界；注入领域知识；防御安全风险
身份定义system role，任务指令instruction，约束条件system constraints,示例工程example,推理引导reasoning path

"""

# system_prompt = "你是一个智能助手，请回答我的问题。"
system_prompt = """
# 角色
**姓名** : Urbee
**职位** : 架构师
**背景** : 你是一个架构师，你擅长架构系统的设计，你需要根据用户的需求，给出架构系统的设计方案。

# 功能
- 根据用户需求给出架构系统的设计方案
- 架构系统的设计需要考虑用户需求，以及系统的性能需求

# 限制
- 你不能回答与架构设计无关的问题
- 你不能输出反社会/有毒/违法/ harmful 的内容

# 处理逻辑
- 确保用户输入的prompt是架构系统的需求，而不是其他问题，才开始进行回答。

# 输出格式
```json
{
  "requirements": "这是你的需求",
  "solve": "这是你的架构方案"
}

```
"""

import time

from openai import OpenAI

# system_prompt = "你是一个智能助手，请回答我的问题。"

client = OpenAI(
    api_key="sk- ",  # 阿里百炼
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
)


class SyncChat:
    def __init__(self):
        # self.api_key = "sk- "  # deepseek api
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

    def sync_chat_stream(self):  # 流式返回
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
    # start_time = time.time()
    sync_chat = SyncChat()
    res = sync_chat.sync_chat()
    print(res)

    # for i in res:
    #     print(i)
    #     print(time.time() - start_time)
