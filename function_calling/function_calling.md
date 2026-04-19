# FunctionCalling(函数调用)
**描述** :大模型与外部系统交互的核心机制，使模型能够：
1. 理解用户请求中隐含的操作需求
2. 生成结构化API调用指令
3. 整合API执行结果生成自然语言响应
在本质上使自然语言处理与程序化接口间建立“神经-符号”转换层

# 大模型交互角色

- system: 系统角色，主要用于系统提示词
- user: 用户角色，用户输入的指令
- assistant: 助手角色，模型生成的指令及回答作为助手角色的回复
- tool: 工具角色，主要保持执行function后的结果

# MCP Protocal
MCP(Model Call Protocol) 是大模型与外部系统交互的协议
mcp 服务器里有tools执行操作, resources获取数据, prompts生成模板
使工具调用不仅仅局限于本地，借助mcp服务器，工具也可以调用其他外部工具

**数据流向**：
AI应用-请求用protocol-MCP服务器-工具-返回-MCP服务器-AI应用-返回-用户

