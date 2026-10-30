# 按需调用，不强制逐层读取

工具名称由宿主加命名空间，业务名为 Read/Write/Delete/Configure。

```json
{"query":"单位","view":"overview"}
```
直接返回批准的数据入口及字段。随后写入时可省略name。

```json
{"rows":[{"Id":"marine","Health":50}]}
```
Write返回plan后，Write只用`{"action":"apply","plan":"返回值"}`提交。

```json
{"import_file":"Incoming/MapUnits.json","mapping":{"Id":"UnitId","Health":"HitPoints","Name":"DisplayName","Advisor":"AdvisorId","Description":"Text"}}
```
输入来自本地文件，程序批量映射。不自动新建数据表或增删字段定义。

```json
{"query":"zero copy selected entities","view":"overview","select":false}
```
临时看依赖，不改变维护目标。

```json
{"name":"A::Normalize","old_code":"return x + 0;","new_code":"return x;"}
```
正常编辑可以缩短。并非token数量必须增长。

```json
{"kind":"function","new_code":"#include <algorithm>\nint A::ClampStep(int x) const { return std::clamp(Normalize(x),0,100); }"}
```
一个CPP实现自动同步普通类H声明；不自动设计Blueprint/RPC语义。

```json
{"kind":"comment","name":"A::Normalize","fields":{"brief":"返回归一化的输入。"}}
```
省略的参数、返回和详细说明保留。

Delete示例：`{"name":"Units","keys":["worker"],"reason":"明确移除该记录"}`；必须本机批准当前计划。
Configure示例：status、target、parent/child、lock/lock_status、check_comments、export_docs、validate。
Read(view=changes,base=WORKTREE,target=PLAN)看函数级计划；数据计划用Read(view=plan)。
Read(view=history)读事务；恢复、批准、解锁由GUI用户进行，无MCP旁路。
