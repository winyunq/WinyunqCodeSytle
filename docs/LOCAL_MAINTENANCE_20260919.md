# 2026-09-19 本地维护修订

基于 UnrealMaintenanceMCP 0.1.0 交付源码。本修订不是 Doxygen 内核更改。

## 修复

- maintenance/profile.py：路径授权使用平台路径匹配语义，修复 Windows 规范化路径与大小写敏感 glob 不一致的问题；保留原范围限制。
- doxygenue/transactions.py：原子替换保留既有文件名大小写；差异与提交结果使用保留磁盘名称的 POSIX 相对路径。
- doxygenue/changes.py：PLAN 覆盖复用既有文件路径身份，避免同一 Windows 文件产生大小写不同的两个快照键。
- maintenance/engine.py：精确类、结构体、联合体、命名空间文档使用既有 Doxygen 实体 inventory；避免类名被误解析为同名构造函数。没有增加第二套 C++ 解析器。
- tests/test_workflows.py：增加类名与构造函数文档区分测试。原有大小写、差异、回滚测试保留。
- ue-maintenance Skill：同步已确认约束不得被擅自弱化的通用维护要求。具体游戏业务规则仍属于对应项目的源码文档。

## 验证与已知限制

Windows / Python 3.10 / Doxygen 1.10.0 下，67 项测试中 66 项通过，1 项仅适用于 POSIX 的测试跳过。真实 stdio 流程验证了函数接口和普通函数体读取、类注释预览/写入/回读、HTML 导出，非注释 token 与预处理指令不变。

大型 Unreal Execute 的函数体仍被既有词法边界检查拒绝，尚未覆盖所有宏/条件编译组合。后续性能分析需要补齐该读取能力，不能因此改造游戏运行逻辑。工具用于读取和维护语义；运行性能仍须以实际采样验证。

## 维护与分发

本地运行目录中的修复是源码修改，已收入重打包内容和更新后的 MANIFEST.json。分发按清单打包，不包含机器配置、项目源码、状态数据库、请求记录、索引缓存或 .py.original 备份。原交付压缩包保持不变。开源许可沿用 NOTICE.md 的现有说明，本次未指定许可证或发布到远端。
