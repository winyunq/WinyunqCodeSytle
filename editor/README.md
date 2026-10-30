# UE 编辑器内的 DataTable 适配

**实现已包含；本次仅API契约替身测试，未在实际UE编辑器执行。** 不把调用了一个Python同名函数当成UE实测。

## 连接真实工程

1. GUI选择`.uproject`所在工程根目录，不是任意插件子目录。选择含ue_datatable绑定的本地profile。
2. 实际UE编辑器启用Python Editor Script Plugin及Editor Scripting Utilities。先保存用户的资产修改并结束PIE。
3. GUI点“UE桥接启动脚本”，会在状态目录外置生成StartEditorBridge.py；通过UE的执行Python脚本功能运行它。
4. 编辑器内验证当前project_dir与所选根相同，并加载同一个profile。它使用Slate后置回调每秒最多4次处理本地邮箱；不是游戏Tick，没有新增游戏模块或运行代码。
5. MCP `Read(name="UnitTable",view="overview")`会向真实编辑器请求导出。编辑器不在线/配置不同/资产不存在会报错，不返回样例。

## 写入如何保留旧内容

先完整读取旧表在程序内合并，只把摘要给AI。使用既有行UStruct，主键Name按FName常用大小写不敏感规则匹配。

UE的`fill_data_table_from_json_string`会清空旧表再导入，所以本实现不会把几条增改直接交给它：完整合并→检查旧行不丢失→版本对比→编辑器事务→导入→严格回读→保存→再次回读。省略记录和字段必须仍在；不接受“UE返回true”就当成功。

拒绝未保存资产、PIE、过期请求、旧版本、未知资产绑定、任意代码执行。写入失败尝试从before.json恢复并保存。回滚失败留下needs_recovery回执并阻止继续写入；客户端超时不宣称成功或回滚。

## 支持与不支持

只支持同一工程`/Game/...`中的既有DataTable行增改和明确删除。不支持创建表、升级UStruct、SQLite/远端数据库、StringTable、任意DataAsset、Blueprint行为图、材质图、内容重命名重定向或原始星际地图解析。

本地邮箱没有网络端口，也没有eval/exec或模型发Python的入口。但是同账号任意写盘不是安全隔离边界；请结合操作系统限制与Skill，不把本机点击当成身份认证。

复杂数据的归一化、行顺序、FText和资产引用需要真实工程验收。当前严格相等可能保守拒绝合法归一化，不能用放宽比较静默吞掉字段。发生问题应修适配/映射，而不是改游戏C++绕过。

## 核对的官方API契约

- Epic DataTableFunctionLibrary (Python API 5.7)：https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/DataTableFunctionLibrary?application_version=5.7
- Epic EditorAssetLibrary (5.7)：https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/EditorAssetLibrary?application_version=5.7
- Epic EditorLoadingAndSavingUtils (5.7)：https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/EditorLoadingAndSavingUtils?application_version=5.7
- Epic EditorLevelLibrary (5.7)：https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/EditorLevelLibrary?application_version=5.7

API版本核对不是5.7/5.8实际运行认证。`tests/test_contracts.py`明确标注编辑器替身，不混入真实UE测试数量。
