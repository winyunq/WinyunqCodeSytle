# 使用说明书：UnrealEngineCPPCodingMCP 0.1.0

## 1. 哪些东西由谁决定

用户为真实工程选择一次维护配置，决定既有数据入口、可改源码范围和验证命令。没有配置就是只读。AI 不能通过 Configure 改成更宽的权限，不能批准删除或解锁。

配置是工程适配信息，不是要求每次填写的方案审批表。一个项目可以保留“内容维护”和“源码维护”两份配置。真实项目必须选择自己的入口和字段；演示按钮不能自动授权真实项目。

Skill 使用已有信息判断需求落在哪里。能修改现成数据就不编程；能调用现有接口就不新造机制；确实有缺口再扩展原系统。工具负责精确操作和已有约束，不声称能独立推断所有业务职责。

## 2. 启动、安装与 Codex

双击 Start-GUI.cmd；或 `python Run.py gui`。需要 Python3.10+/Tk。代码能力额外需要 Doxygen；构建命令根据实际工程配置。数据能力不依赖 Doxygen。

本地安装：

```powershell
py -3 tools\install.py --destination "D:\Tools\UnrealEngineCPPCodingMCP-0.1.0"
```

目标目录必须不存在。先核对整个 MANIFEST.json，再复制；拒绝覆盖。卸载只需删除该安装目录；状态数据库在单独用户目录，不会自动删除。升级安装新目录，原有配置和项目不动。安装器本次没有 Windows 实机验收，也没有捆绑 Python/TeX。

GUI“Codex配置/Skill”生成适用于当前路径的配置文本，不覆盖 config.toml。例子仅说明结构：

```toml
[mcp_servers.UnrealEngineCPPCodingMCP]
command = 'C:\Python313\python.exe'
args = ['-u', 'D:\Tools\UnrealEngineCPPCodingMCP-0.1.0\Run.py', 'server', '--project', 'D:\UE5Project\Winyunq', '--profile', 'D:\MaintenanceProfiles\Winyunq-content.json']
```

安装本项目的 Skill：

```powershell
py -3 tools\install_skill.py --project "D:\UE5Project\Winyunq"
```

写入 `.agents/skills/ue-maintenance`。存在不同内容时，在写入任何文件之前拒绝；不修改你的其他 Skill、AGENTS.md 或 Codex 配置。相同版本重复安装无变化。实际 Codex 宿主在本环境未启动，验证使用同样 stdio 的测试客户端。

## 3. 读：现在需要多少就一次取多少

以下代码块是 tools/call 的 arguments，不再重复外层 JSON-RPC。

Read 搜索一个简短候选：

```json
{"query":"单位"}
```

找到绑定的表，返回名称、简短说明和行数，不返回全部记录。内容模式有数据命中时，不为这个查询构建代码索引。没有数据命中，可以报告源码候选或源码索引不可用；不能因此获得源码写入权限。

一次读足表结构与用法证据：

```json
{"query":"单位","view":"overview"}
```

读取少量实际数据：

```json
{"name":"Units","view":"rows","where":{"Id":"marine"},"fields":["Name","Health"],"limit":1}
```

读取代码接口，可直接选 overview/details/documentation/code/raw/comments。默认 overview；搜索缺省为 brief。details/documentation 使用完整解析文档，而不是 brief 的扩写。raw 是当前对象原貌，不是整文件回退。没有必要逐层调用。

```json
{"query":"zero copy selected entities","view":"overview"}
```

`uses` 返回文本位置，不是完整的语义引用关系或调用图。`project` 包含 Content、配置、源码、描述符，以及 Build.cs 中能直接读取的字面依赖；不执行任意 C# 求真实构建依赖。

Target 只补缺省。搜索单项默认记住对象；`select:false` 可不改变它。显式 `name/path` 默认只覆盖本次。多个候选请求 `limit:10`，不会自动选中。已有名称直接操作，不必先设置 Target。

## 4. 写：增改既有数据，先预览再提交

Write 的 rows 是按主键 upsert，不是整表替换：

```json
{"name":"Units","rows":[{"Id":"marine","Health":50}]}
```

这只改变 Health，其他字段和 worker 等未提供的记录保留。新记录必须满足表的 required/type/reference 规则；不猜默认值、不创建占位引用。嵌套对象合并，数组字段属于显式字段替换，不是表行增删。JSON 未改变行的原文保留，改变行由程序排版；CSV 保留表头次序、BOM、换行，重新进行标准 CSV 引号转义，不保证原有引号外观逐字节不变。

大量输入交给程序读文件：

```json
{"name":"Units","import_file":"Incoming/MapUnits.json","mapping":{"Id":"UnitId","Advisor":"AdvisorId","Name":"DisplayName","Health":"HitPoints","Description":"Text"}}
```

源文件必须位于本地项目内，是已有 JSON 数组或标准逗号 CSV。这里不是星际地图专有格式解析器。返回改了多少行和最多20条摘要；长字段/大量列继续缩略，完整计划在本机 `plans/<plan>.json`。省略摘要不等于省略修改。GUI/用户删除审批读取完整计划。

预览返回 plan，然后 Write 提交：

```json
{"action":"apply","plan":"刚才返回的计划号"}
```

这个计划号是版本绑定的修改事务，不是 target_id。提交不接收替换后的新载荷。源文件、目标文件、锁、配置、受信文件变化会拒绝。重复导入相同值返回 unchanged，不产生重复项。

内容模式拒绝 code/function/include/comment 等运行源码写入；未知数据格式报缺少适配，不借机允许改 C++。

## 5. 写：维护代码，复用原来的机制

普通缩短编辑：

```json
{"name":"A::Normalize","old_code":"return x + 0;","new_code":"return x;"}
```

局部 old_code 必须在定位到的目标内唯一匹配。省略兄弟函数不会删除它。跨注释的替换会拒绝，应缩小片段，不能让 AI 抄回全文件。

只写 CPP 添加原类成员：

```json
{"kind":"function","new_code":"#include <algorithm>\nint A::ClampStep(int x) const { return std::clamp(Normalize(x),0,100); }"}
```

已支持、可唯一定位时自动同步 H 与 CPP，在同一计划中展示。复杂模板、宏生成、模糊重载、Blueprint/RPC 生成方法或全调用者联动并非通用支持。不能将一次原生示例通过当作 UHT/整个 UE 工程通过。

只修改源码注释字段：

```json
{"kind":"comment","name":"A::Normalize","fields":{"brief":"按现有策略归一化输入。"}}
```

参数/返回说明未提供则保留，格式交给程序；AI 不需手工拼星号或另造 @brief 字符串协议。读取概览会保留能识别的 UFUNCTION 说明符，因为它们可能影响正确调用，不把它们作为注释装饰删除。

`review_signals` 是新增 new/delete/static/Tick/常见扫描标记的词法信号，不是自动复杂度证明。只有用户在 profile 声明的 forbid_added_tokens 是硬门禁；正常循环、分配并非全禁止。真正有任务成本约束时，使用工程自己的验证命令，不能只靠编译。

## 6. 删除、锁、失败与恢复

Delete 需要独立请求：

```json
{"name":"Units","keys":["worker"],"reason":"本次明确移除该单位记录"}
```

预览后，GUI“锁/审批/恢复”中审阅并批准这份具体计划；再 Delete apply。Write 不能提交 Delete 计划，理由文本不是身份凭证。未审批、过期、源码或锁变化都不能提交。有关联的已绑定数据仍引用某主键时，先维护引用，不能直接删除。

Configure lock 可加锁；解锁只在本机用户界面执行。GUI 能读取同一状态库中的 Codex 待审批计划。UI 不会把“用户让我修改”自动理解成“用户已经解锁”。

文件事务在本地生成备份/日志。已配置验证失败时，事务文件回滚；失败输出直接给有上限的真实日志尾部。验证命令可能有自己的输出/副作用，源码回滚不等于撤销整个外部构建世界。进程崩溃不是多文件原子提交；存在未结束事务时应查看 journal，不能盲目重试。

GUI 的恢复仅在当前文件仍与记录的修改后字节一致时恢复源文件。UE 资产有独立回执/备份和编辑器事务，不复用文件字节恢复按钮。超时状态未知需检查回执。

## 7. 检查、函数差异、导出

```json
{"view":"changes","base":"WORKTREE","target":"PLAN"}
```

这是 Read。源码计划按函数归类；数据/资产计划按记录归类。Git HEAD/INDEX/WORKTREE 和本地版本比较由保留的引擎实现；未归类改动仍显示，不假装全是函数。没有 Git 时仍可查看当前计划。

Configure 示例：

```json
{"action":"check_comments","path":"Source","limit":20}
```

```json
{"action":"validate"}
```

```json
{"action":"export_docs","output_format":"html"}
```

源码文档检查复用 Doxygen 的参数/段落语义；保留既有引擎检查路径。导出是本地文档预览，不宣称正式发布门禁；GUI 没有用导出成功冒充代码/文档完整。PDF 需要额外 XeLaTeX，核心安装和本轮演练没有生成 PDF。

## 8. 真实 UE 与当前边界

只有真实 UE 编辑器连接，ue_datatable 绑定才可读写。编辑器操作使用官方 Python API，完整读取旧表、合并、验证、提交；导入前不得存在用户未保存编辑或 PIE。读回不一致时尝试回滚，不接受布尔返回值就称成功。详见 editor/README.md。

本轮真实执行：标准库 JSON/CSV、stdio MCP、Tk/Xvfb、Doxygen1.18、原生 C++ 编译与任务断言。DataTable 测试使用 API 契约替身，不能据此声称通过真实 UE。Windows/Codex/UE 整工程都需要本机验收。

全项目单次文件上限16 MiB，表最多100000行，内联数组最多1000项；更多行用import_file。代码首次索引和变化后重建可能昂贵；没有大型 UE 性能数据。文本查询和少量本地同义词不是任意自然语言语义检索。别名和 bindings 可由用户为原工程一次配置，不是自动证明所有用途。

模型经其他同账户工具直接写盘可绕过本工具，因此 Skill 也明确禁止绕过。需要防止恶意同账户行为时使用 OS/服务隔离，此包不是隔离层。
