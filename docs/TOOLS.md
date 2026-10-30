# 实际 MCP 四工具

对应 docs/TOOLS.json，取自正在运行的 server 的 tools/list。以下不引入第五个顶层工具。

| 工具 | 主要参数 | 默认值／行为 | 真实边界 |
|---|---|---|---|
| Read | query 或 name/path；view；limit/offset；where/fields；select；part；base/target/detail | 直接读。查询默认1项brief；显式对象默认overview | 数据、源码共用；uses为文本证据；没有整文件失败兜底 |
| Write | name/path可省；kind；rows 或 import_file/mapping；old_code/new_code；fields；action/plan | preview再apply，普通缩短是编辑 | profile限制；只更新支持对象；不新造绑定/项目数据系统 |
| Delete | name/path可省；kind；keys 或 old_code/comment_id；reason；action/plan | preview→本机批准→apply | reason不是授权；不能由Write提交；引用、锁、版本继续校验 |
| Configure | action；name/path/kind；reason；output_format；limit | action=status | 不提供解锁、审批、改profile、任意命令执行 |

## Read 视图

- auto/brief/overview/details/documentation：选择信息密度，不强迫按序调用。
- code/raw/comments：目标实现/原貌/指定注释层。
- rows：绑定表按条件、字段和页读取。表brief不附全量记录。
- project：跨Source/Content/配置/UE描述符和字面模块依赖清单。
- uses：文本位置证据，不是语义调用图。
- changes：Git或当前PLAN的对象级差异。
- plan：当前预览摘要；history/inventory：源引擎事务与输入信息。

## Write 对象

kind=code/comment/data/asset/function/include。不传kind时可由已有数据名称、rows/import_file或Target补全；函数CPP定义建议显式kind=function。

operation=modify/add/function/include。`modify_member` 仅增改单个字段的 `UPROPERTY(...)` 或函数的 `UFUNCTION(...)` 前置标记；`modify_members` 可在一个事务中增改同一类型的多个字段标记。两者都比较旧、新声明并拒绝字段或函数签名变化。注释fields单独修改；函数体没有提供的其他部分保留。asset使用已绑定ue_datatable并要求编辑器连接。

## Delete 对象

kind=data/asset/code/symbol/comment/include。数据明确keys；源码/注释明确原片段或已有注释定位。独立符号删除受保留引擎安全范围限制。

## Configure 动作

status、target、parent、child、scope、abort、lock、lock_status、validate、check_comments、export_docs、reindex、approvals、policy。

scope仅改变源码查找范围，不扩展批准路径、取消锁或扩大数据绑定。切换范围/Target清除旧计划。policy为文档规则读取；运行维护授权profile只在启动时选择，MCP不能改。

## 实际调用例子

```json
{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"Read","arguments":{"query":"单位","view":"overview"}}}
```

默认返回一份 structuredContent，content为空数组；工具错误使用isError文本。旧客户端可启动 `--response-mode text`，提供一份JSON文本而不再同时发送结构化副本。原始JSON-RPC日志里的字符转义不等于要求模型再解析自造语法；不要将GUI原始通信日志当作默认模型内容。

name/path是可选缺省覆盖，不是target_id。plan是不可变修改计划，必须来自当前会话，不能跨会话粘贴后提交。comment_id仅用于选定内部多条注释，不能代替权限。
