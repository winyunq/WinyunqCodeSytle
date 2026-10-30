# UnrealEngineCPPCodingMCP 0.1.0

面向 UE5 工程的 C++ 代码 MCP。

这是新的独立交付，不覆盖 DoxygenUnrealEngine 0.3.0，也不是 Doxygen 内核 fork。保留了既有、已验证的 Doxygen/C++ 局部编辑引擎；新入口把项目数据与源码放进同一套 **Read / Write / Delete / Configure**。Skill 决定解决问题的顺序，程序执行可验证的范围、字段、版本、锁和任务测试。

## 分层功能架构

![分层功能架构](docs/architecture.svg)

<details>
<summary>Mermaid 源码</summary>

```mermaid
flowchart TB
    subgraph API[" "]
        direction LR
        L1["<div style='width:190px;height:350px;display:flex;align-items:center;justify-content:center;font-size:14px;line-height:20px'><div><b>MCP 功能入口</b><br/>接收维护请求<br/>提供读、写、删、配置功能</div></div>"]
        READ["<div style='width:190px;height:350px;font-size:14px;line-height:20px'><b style='color:#1d4ed8'>读 · Read</b><br/><br/>工程与绑定清单<br/>符号与数据搜索<br/>符号概览与详情<br/>源码与原始内容读取<br/>注释与 Doxygen 文档读取<br/>数据行查询与字段筛选<br/>符号引用定位<br/>修改差异对比<br/>变更历史与维护清单<br/>修改计划读取</div>"]
        WRITE["<div style='width:190px;height:350px;font-size:14px;line-height:20px'><b style='color:#1d4ed8'>写 · Write</b><br/><br/>源码新增与局部修改<br/>新增符号与成员<br/>单个与批量成员反射标记<br/>函数声明与定义编辑<br/>include 增加与修改<br/>Doxygen 字段与注释编辑<br/>局部初始化值修改<br/>数据记录增加与修改<br/>JSON/CSV 导入与字段映射<br/>坦克目标修改<br/>坦克资产路径替换<br/>聚焦坦克路径替换<br/>聚焦坦克描述替换<br/>修改预览与提交</div>"]
        DELETE["<div style='width:190px;height:350px;font-size:14px;line-height:20px'><b style='color:#1d4ed8'>删 · Delete</b><br/><br/>代码片段删除<br/>源码符号删除<br/>注释删除<br/>include 删除<br/>数据与资产记录按主键删除<br/>旧 INI 配置清理<br/>删除预览与提交</div>"]
        CONFIGURE["<div style='width:190px;height:350px;font-size:14px;line-height:20px'><b style='color:#1d4ed8'>配置 · Configure</b><br/><br/>维护状态读取<br/>缺省目标设置<br/>父子目标与作用范围<br/>维护任务中止<br/>数据锁定<br/>锁状态查询<br/>编译与任务验证<br/>UE 本地化检查<br/>Doxygen 注释检查<br/>HTML/LaTeX/PDF 文档导出<br/>Doxygen 索引重建<br/>审批状态读取<br/>权限策略读取</div>"]
        L1 ~~~ READ ~~~ WRITE ~~~ DELETE ~~~ CONFIGURE
    end

    subgraph PROCESS[" "]
        direction LR
        L2["<div style='width:190px;height:70px;display:flex;align-items:center;justify-content:center;font-size:14px;line-height:20px'><div><b>代码与数据处理层</b><br/>按风格规则处理源码<br/>按项目绑定处理数据</div></div>"]
        SOURCE["<div style='width:190px;height:70px;font-size:14px;line-height:20px'><b style='color:#1d4ed8'>源码解析与定位</b><br/><br/>符号定位 · 源码结构解析</div>"]
        COMMENTS["<div style='width:190px;height:70px;font-size:14px;line-height:20px'><b style='color:#1d4ed8'>注释与文档处理</b><br/><br/>Doxygen 字段读取与编辑</div>"]
        EDIT["<div style='width:190px;height:70px;font-size:14px;line-height:20px'><b style='color:#1d4ed8'>源码编辑与同步</b><br/><br/>局部编辑 · CPP/H 同步</div>"]
        DATA["<div style='width:190px;height:70px;font-size:14px;line-height:20px'><b style='color:#1d4ed8'>项目数据适配</b><br/><br/>JSON/CSV · UE 数据表</div>"]
        L2 ~~~ SOURCE ~~~ COMMENTS ~~~ EDIT ~~~ DATA
    end

    subgraph SUPPORT[" "]
        direction LR
        L3["<div style='width:190px;height:70px;display:flex;align-items:center;justify-content:center;font-size:14px;line-height:20px'><div><b>基础能力层</b><br/>提供索引、检查与存储</div></div>"]
        DOXYGEN["<div style='width:190px;height:70px;font-size:14px;line-height:20px'><b style='color:#1d4ed8'>Doxygen</b><br/><br/>符号与文档索引</div>"]
        CPP["<div style='width:190px;height:70px;font-size:14px;line-height:20px'><b style='color:#1d4ed8'>C++ 检查</b><br/><br/>词法与源码结构检查</div>"]
        VALIDATION["<div style='width:190px;height:70px;font-size:14px;line-height:20px'><b style='color:#1d4ed8'>编译与任务验证</b><br/><br/>运行项目配置的验证命令</div>"]
        STORE["<div style='width:190px;height:70px;font-size:14px;line-height:20px'><b style='color:#1d4ed8'>SQLite</b><br/><br/>状态与变更历史存储</div>"]
        L3 ~~~ DOXYGEN ~~~ CPP ~~~ VALIDATION ~~~ STORE
    end

    API --> PROCESS --> SUPPORT

    classDef layer fill:#eef2f6,stroke:#475569,color:#111827
    classDef module fill:#ffffff,stroke:#1d4ed8,stroke-width:2px,color:#111827
    classDef feature fill:#ffffff,stroke:#64748b,color:#111827
    classDef row fill:#ffffff,stroke:#94a3b8,color:#111827
    class L1,L2,L3 layer
    class READ,WRITE,DELETE,CONFIGURE module
    class SOURCE,COMMENTS,EDIT,DATA,DOXYGEN,CPP,VALIDATION,STORE feature
    class API,PROCESS,SUPPORT row
```

</details>

## 先运行实际例子

需要 CPython 3.10+。GUI 需要 Tk（Windows 官方 Python 安装选项 Tcl/Tk）；运行产品不需要 pip。数据模式不需要 Doxygen。代码功能需要 Doxygen；便携 C++ 验收需要 g++ 或 clang++，不是 UE 构建。

1. 解压，双击 `Start-GUI.cmd`，点击“新建演示副本”。它只复制包内例子到新临时目录。
2. 搜索“单位”，选 `overview`。看到既有 Units 数据入口，增改页填 rows 或源文件映射，先预览再提交。切勿把演示字段照搬到实际游戏。
3. 代码演示需要 Doxygen：已有程序可选择路径；没有则运行 `Bootstrap-Doxygen.cmd`（下载固定官方 Windows 版本并核对 SHA256）。在演示中切换“代码维护模式”。
4. `Run-Demo.cmd` 自动重放三种任务及反例，最后打印实际项目副本和日志路径。`Run-Tests.cmd` 跑回归。测试没有安装 Doxygen 时，代码类测试会明确跳过，不能据此声称全部路径通过。

Linux/macOS：`python Run.py gui`。显式配置：

```sh
python Run.py server --project /path/to/project --profile /path/to/approved-profile.json --doxygen /path/to/doxygen --state-db /outside/project/state.sqlite3
```

## 交付包含什么

- 既有 JSON/CSV 表：按主键增改；省略记录和字段保留；映射批量文件，不经过模型抄写全部数据。主键、类型、引用、源码范围和任务测试由用户选定的本地 profile 决定。
- 既有 C++：搜索 brief/概览/完整文档、正常缩短编辑、普通成员 CPP/H 同步、include、源码注释字段、函数差异；真实编译/任务验证失败回滚。
- UE：保留 UFUNCTION 调用语义、模块依赖文字证据、Content/配置可见；附编辑器内执行的真实 DataTable 适配器。该适配器在此环境只执行 API 契约测试，未在 UE 中执行。
- 本地 GUI：真实 MCP 请求和返回；锁、独立删除审批、源码事务恢复；Codex 配置文本与 Skill 安装。默认只有一份结构化返回，旧客户端可启用单份 text 模式。
- Skill：数据能表达就改数据；接口能满足就调用；确实缺少能力才扩展拥有该职责的系统。没有强制阅读阶梯、target_id、搜索凭证或每次填写的设计报告。

## 核心限制

这是有明确支持范围的实现，不是自动架构证明器。`forbid_added_tokens` 只是用户已知模式的词法门禁；未知的职责重复依赖工程证据、Skill 判断与实际任务验证。附带的计数成本测试只是一个反例验收，不是任意项目自动生成的性能标准。

不支持 SQLite/SQL 写入、INI 写入、星际地图二进制格式解码、任意 UAsset/Blueprint 图修改、全量 C++ 调用点重构或完整 UHT 语义。输入文件单个最多16 MiB、表最多100000行；源码索引首次扫描和变化重建的整 UE 工程性能没有测量。不要以例子的速度推断真实项目。

同一系统账户的任意 Shell 权限可以绕开此 MCP。GUI 点击不是 OS 身份认证。没有连接实际 UE 时，资产操作明确失败，不伪造结果，也不改 C++ 兜底。

## 文档

- [生成开发者/用户网页、五类 API 和增量翻译](docs/WEBSITE_ZH.md)

- [使用手册](docs/MANUAL_ZH.md)
- [四工具实际清单](docs/TOOLS.md) / [运行中 tools/list](docs/TOOLS.json)
- [配置已有项目](docs/PROFILE_ZH.md)
- [UE 编辑器 DataTable 通道](editor/README.md)
- [可控范围与验收](docs/ACCEPTANCE_ZH.md)
- [Skill](.agents/skills/ue-maintenance/SKILL.md)
- [证据](evidence/README.md)

`Install-Windows.cmd` 是 Python 本地安装脚本，不是自包含 Setup.exe；它校验清单，安装到新的版本目录，不覆盖旧目录，不改用户项目。没有在 Windows 做过安装验收。见 NOTICE.md 的来源和许可边界。

## 本地维护修订

[2026-09-19 修复、验证与已知限制](docs/LOCAL_MAINTENANCE_20260919.md)。

## 本地化遗漏检查

`Configure(action="check_localization", name="Game")` 读取项目原生 `Game.manifest` 与中文、英文 `Game.archive`，报告缺失或空译文、源文本变化及中文原文换行不一致。返回 `gathered`、`missing`、带来源位置的 `gaps`；空采集报错，不能当作零遗漏。先使用 UE Localization Dashboard 的 Gather Text 更新采集结果，再检查；导入和编译仍由 UE 原生本地化工具负责。

代码预览新增 `FText::FromString(TEXT(...))`、`FText::FromString(FString::Printf(TEXT(...)))` 或 `AsCultureInvariant` 普通文字时，返回 `localization_warnings`，提示使用已有本地化 FText、LOCTEXT/NSLOCTEXT 或字符串表身份。检查不修改语言、资产、权限或运行时 UI。

需要按界面检查时可使用 CLI：

```sh
python tools/check_localization.py --manifest PROJECT/Content/Localization/Game/Game.manifest --archive zh=PROJECT/Content/Localization/Game/zh-Hans-CN/Game.archive --archive en=PROJECT/Content/Localization/Game/en/Game.archive --namespace Winyunq.UI
```

`--location` 支持原生采集来源通配符；`--project PROJECT --editor UnrealEditor-Cmd.exe` 可调用 UE 原生采集并把检查中间文件放入 Saved/LocalizationChecks。发现遗漏时退出码为 1。原生采集覆盖有身份的 FText；动态 FString、运行时拼接或明确不可本地化文本仍需核对实际界面。代码预览的字面量提示仅检查本次新增片段。MCP 服务重启后加载新增动作和提示。
