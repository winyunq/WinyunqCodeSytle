# 证据说明

- replay/RESULTS.json：三项真实MCP任务、负对照、源码hash与实际原生运行计数。
- replay/MCP-RUN.json：完整真实请求、返回、往返时间和字符数。
- gui/：实际Tk窗口截图、关键帧动画和GUI客户端请求。不是设计稿。
- TEST_RESULTS.txt：本轮从最终源码执行的测试结果；Package-Tests.txt为解压最终源码包后复跑。

tests/test_contracts.py中的EditorContracts使用Python API替身模拟UE官方接口，验证适配合并、拒绝和恢复逻辑。它们不是UE编辑器集成测试；真实UE执行状态为false。

字符统计只描述工具传输量；不同MCP宿主如何传给模型、具体模型token没有在这里测量。GUI显示token为粗略估算，不是计费。
