# 原生 MCP 调用

工具名称由宿主加命名空间，业务名为 `Read`、`Write`、`Delete` 和 `Configure`。

```json
{"query":"Normalize"}
```

得到符号后可用 `name` 或 `target` 定位。`view` 支持 `declaration`、`definition`、`documentation`、`members` 和 `references`。

```json
{"kind":"comment","target":"A::Normalize","fields":{"brief":"返回归一化的输入。"}}
```

预览返回 `plan` 后，用 `Write` 提交 `{"action":"apply","plan":"返回值"}`。新增成员传 `kind: "member"` 和 `declaration`。

删除符号用 `Delete`，服务检查实际引用。整段注释和源码片段的删除沿用本地审批。

网页使用 `Configure(action=generate_website)`。
