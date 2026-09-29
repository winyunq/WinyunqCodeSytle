# 源码备份清单

目的：保存本次维护的 UnrealMaintenanceMCP 本地化检查及其原接口接入，供本地版本恢复。

| 仓库相对文件路径 | 用途 | 必须备份的原因 |
|---|---|---|
| `.gitignore` | 精确源码范围 | 默认忽略未列入清单的结果及临时文件 |
| `GIT_BACKUP.md` | 备份清单 | 记录源码与外部依赖 |
| `UnrealMaintenanceMCP/tools/check_localization.py` | 原生文本身份与译文检查 | 检查空采集、缺译、旧源文本及换行，并提示新增不可采集字面量 |
| `UnrealMaintenanceMCP/maintenance/engine.py` | 既有维护入口 | 接入 Configure 检查和 Write 预览提示 |
| `UnrealMaintenanceMCP/maintenance/protocol.py` | MCP 接口定义 | 使客户端能调用新增检查动作 |
| `UnrealMaintenanceMCP/tests/test_localization.py` | 行为验证 | 复现空采集、缺译、身份冲突、源文本换行及 MCP 调用 |
| `UnrealMaintenanceMCP/README.md` | 运行与接口说明 | 给出原生采集前提、调用方式和覆盖边界 |

既有已跟踪工具源文件由原索引保留，本次按上述文件逐项提交。所列文件均小于 10 MiB。

排除：报告、日志、缓存、Saved、SQLite 状态库、导出 PO、下载依赖、编译与打包结果、凭据和机器 profile。运行依赖既有工具源码及 CPython；原生采集依赖用户 UE 安装及项目资产。UE 位于 D:/UE_5.8，项目位于 D:/UE5Project/Winyunq，个人 profile 保存在 C:/Users/winyunq/Tools/UnrealMaintenanceMCP-0.1.0/UnrealMaintenanceMCP/local-winyunq。该本地 Git 提交不代表独立磁盘备份。
