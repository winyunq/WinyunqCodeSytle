# 一次接入已有工程

profile 是用户在启动/GUI中选定的本地文件，不是模型每次提交的授权文本。修改后需重新连接，旧计划失效。建议保存在工程外，受信测试文件在工程内时列入 pinned_files。

## 数据模式最小例子

以下假设工程本来就使用 Content/Data/Units.json；它不会创建运行时加载器。

```json
{
  "version":1,
  "label":"只维护现成单位数据",
  "mode":"content",
  "data":[{
    "name":"Units",
    "path":"Content/Data/Units.json",
    "format":"json",
    "key":"Id",
    "brief":"现有单位数据和显示文本",
    "fields":{
      "Id":{"type":"string"},
      "Name":{"type":"string"},
      "Health":{"type":"integer","minimum":0}
    },
    "consumers":["Units.json"]
  }]
}
```

format支持json、csv、ue_datatable；对其他文件目前只做输入发现，不进行未经定义的写入。fields取自原数据结构，不能照抄例子。required省略时，新行/修改后的行要求列出的全部字段；可显式调整。支持string/integer/number/boolean/object/array、enum、minimum/maximum、nullable。

references形如 `{"Advisor":"Advisors"}`，引用目标也是已注册的绑定。未知引用拒绝，不生成占位内容；只检查这些显式关系，不声称全工程外键完整。多资产/数据库级ACID未实现；写入单位为单个绑定，不接受跨多个资产的组合事务。

consumers是用于搜索现有用法的文字，不是宣告这张表已在游戏中生效。Read返回实际匹配路径；同名文字证据不能替代真实游戏验证。

别名可选 `"aliases":{"选择数量":["GetSelectedEntitiesView"]}`。本地别名加标识符/Doxygen匹配，不是通用向量语义搜索。

## 维护源码

```json
{
  "version":1,
  "mode":"maintain",
  "code_paths":["Source/MyModule/Public/*.h","Source/MyModule/Private/*.cpp"],
  "require_validation":true,
  "validation":{
    "commands":[["{python}","D:/TrustedChecks/VerifyProject.py","--project","{project}"]],
    "timeout_seconds":300
  },
  "pinned_files":["Tests/ExistingContract.cpp"],
  "forbid_added_tokens":["GetAllActorsOfClass"]
}
```

命令由用户预置，不通过Shell拼接；最多8条，单条超时最多600秒。占位符{project}/{python}/{package}由程序补全。调用UE Build.bat时应由受信包装脚本执行正确的引擎/Target配置，不能把示例g++当成UBT。

forbid_added_tokens只能表达用户已经确定的局部约定：新增该token计数则拒绝。不要无差别禁止所有for/new。未知机制仅是review信号，最终还需要项目的实际行为和成本验收。require_validation只保证运行已配置命令，不保证命令本身足够。

JSON/CSV计划在maintain模式也会运行同一个已配置验证器。数据专用content配置可以没有构建命令，完成schema/CAS/引用核对；这不等于验证了UE游戏消费行为。ue_datatable执行编辑器回读与保存核对，返回editor_roundtrip_checked，不冒充该profile的原生构建通过。

## 资产绑定

在真实工程的profile.data中声明：

```json
{
  "name":"UnitTable",
  "format":"ue_datatable",
  "path":"/Game/Data/DT_Units",
  "key":"Name",
  "brief":"项目既有单位表",
  "fields":{
    "Name":{"type":"string"},
    "DisplayName":{"type":"string"},
    "Health":{"type":"integer","minimum":0}
  }
}
```

只能指向已存在的DataTable。字段必须与该表真实导出的行结构一致；FText、复杂引用或数值归一化不一致时本版保守拒绝。它不会自动修改行UStruct，更不会生成C++来迁就字段。字段不能表示时报告缺口，由用户决定是否扩展原结构。
