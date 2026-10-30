# 生成 API 网页

MCP 和 GUI 都有“生成网页”。项目 profile 的 `documentation` 指定源码、受众、语言和输出目录。生成不修改 C++、头文件或 UE 节点。

```json
{"name":"Configure","arguments":{"action":"generate_website","audience":"both"}}
```

- `developer`：使用配置的 C++ 实现和头文件，包含实现说明和内部文档。
- `user`：只读取配置的公开头文件，展示公开声明、说明、参数、返回值与示例。
- `both`：同时生成上述两种文档。`languages` 可覆盖 profile 中的语言列表。

两种受众都经过 Doxygen XML → 通用网页格式化器，使用统一的导航、搜索、参数表、代码块和语言切换。网页不使用 Doxygen 原生 HTML 模板。

## 项目配置

生成器不定义 API 分类。项目可配置任意数量的 `groups`；未配置时生成一节 Reference。`user_inputs` 默认匹配 `Source/**/*.h` 和 `.hpp`，`developer_inputs` 默认再加入 `.cpp`。分组配置取代对应输入列表；开发者视图可使用 `developer_groups`。

最小 profile 示例：

```json
{
  "version": 1,
  "mode": "maintain",
  "documentation": {
    "title": "My Plugin",
    "languages": ["en", "zh-CN"],
    "user_inputs": ["Source/MyModule/Public/**/*.h"],
    "developer_inputs": ["Source/MyModule/**/*.h", "Source/MyModule/**/*.cpp"],
    "output": "Saved/Documentation/Website",
    "translation_directory": "Docs/TranslationMemory"
  }
}
```

`overview.heading`、`overview.description` 和各分组的 `title`、`description`、`example` 可使用按语言代码索引的文字对象。产品名称、引导文案和分类只放在项目配置中。

LiteRT-LM Unreal 的实际配置保存在插件 `Docs/McpDocumentation.json`。它将现有接口投影为 SimpleChat、MultiChat、NativeSDK、Extensions、Settings 五组；Extensions 标为实验性。这是项目配置示例，不是 MCP 内置分类。

每组的 `headers` 接受相对 glob 字符串，或带 `glob`、`symbols_regex` 的对象。正则选择完整符号名，不用正则重新解析 C++。源码解析与文档字段仍由原有 Doxygen 引擎提供。

```json
{
  "id": "SimpleChat",
  "headers": [
    "Source/LiteRTLMUnreal/API/SimpleChat/**/*.h",
    {"glob":"Source/LiteRTLMUnreal/Public/LiteRtLmFastStart.h",
     "symbols_regex":"::(ChatOne|PreloadOne|NewConversationOne)$"}
  ]
}
```

这使现有头文件可以立即生成网页，未来放入 API 目录的新头文件也会被发现。无需提前移动 API 源码。未匹配的内部函数不进入用户页。

`hidden_parameters` 可隐藏由 UE 自动提供的 WorldContextObject。异步节点由 `async_regex` 和 `async_outputs` 明确显示完成、失败和文本输出。C++ 声明保留在可展开的参考区。

## 增量翻译与命中

参考 LaTeX 翻译状态文件的做法，保留文件哈希、原文、译文、审核状态和生成记录。记录按符号、声明及字段标识，不绑定源码行号。

`translation_directory/<语言>.json` 是可用普通 Read/Write 维护的记录数组：

```json
{
  "id":"稳定字段标识",
  "source_text":"Your message.",
  "source_hash":"当前原文哈希",
  "translation":"你的消息。",
  "translated_source_hash":"译文对应的原文哈希",
  "reviewed":true
}
```

原文未变时精确命中；相同文本可复用已有译文。原文改变后保留旧译文供维护者查看，但网页回退显示新原文，不继续展示已过期的翻译。`state.json` 保存文件哈希、hits/reused/seeded/missing/stale 数量和待翻译 id。

头文件已有的 `@par 中文`、配置的双语分隔正则，以及 UE 的 `ApiLocalization.json` 可以提供初始译文。初始译文仍记录来源原文哈希，后续源注释变化不会被旧种子覆盖。

需要通过 MCP 维护译文时，先创建内容为 `[]` 的语言 JSON 文件，再将其注册为普通 JSON 数据绑定。LiteRT 项目使用 `ApiTranslationsZh`，维护示例：

```text
Read(name="ApiTranslationsZh", view="rows", limit=20)
Write(name="ApiTranslationsZh", rows=[{
  "id":"读取到的id",
  "translation":"更新后的译文",
  "translated_source_hash":"读取到的source_hash",
  "reviewed":true
}])
Write(action="apply", plan="预览返回的plan")
Configure(action="generate_website", audience="user")
```

语言切换不改代码标识、参数名或接口签名。未命中的内容显示原文，并在维护记录中列出；生成成功不代表翻译全部完成。

## 输出

默认输出到 `Saved/Documentation/Website`：

```text
index.html
user/en/                 英文用户页
user/zh-CN/              中文用户页
developer/en/            英文开发者页
developer/zh-CN/         中文开发者页
user-source/xml/         用户头文件的 Doxygen 数据
developer-source/xml/    C++ 实现与头文件的 Doxygen 数据
assets/                  本地 CSS、搜索脚本
manifest.json            输入文件、版本、数量和翻译统计
```

网页使用本地 CSS/JS。可直接预览或交给现有网站部署流程；此操作不自动发布网站，也不替代 UE 编译与游戏验证。

文档数据源：[Doxygen XML](https://www.doxygen.nl/manual/customize.html)。
