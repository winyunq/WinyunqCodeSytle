
### 3.4 特定 `@tag` 的 `{FirstPieceOfText}` 结构化实现

在3.3的基础上，确定了`@tag`与`{FirstPieceOfText}`中间的空格数量。对于某些特定的 `@tag`（例如 `@param`, `@tparam`, `@return`, `@extends` 等），其在 3.3 节中定义的 `{FirstPieceOfText}` 部分往往可以进一步结构化，以包含额外的信息（如类型引用、可见性等），并可能涉及额外的内部对齐计算。

本节描述这些特定 `@tag` 的 `{FirstPieceOfText}` 的结构化实现方式。对于其他`@tag`**忽略此内容**

**核心布局参数 (用于结构化 `{FirstPieceOfText}` 内部的对齐):**

*   `winyunq.targetCharOffset_AdditionalInfoStart_RelativeTo_FirstPieceTextStart = 20`
    *   **定义:** (例如) 附加信息（如 `@ref 类型`）的第一个字符，相对于 `{FirstPieceOfText}` 中核心内容（如参数名）**起始位置**的目标**相对字符偏移量**。
*   `winyunq.minSpaces_BetweenNameAndRef = 1`
    *   **定义:** 核心文本（名称）与追加的 `@ref` 关键字之间的**最小**空格数。
*   `winyunq.minSpaces_AfterRefKeyword = 1`
    *   **定义:** `@ref` 关键字与其后的类型文本之间的**最小**空格数。

**规则 D: `@param`,`@tparam`,`@return` 的 `{FirstPieceOfText}` 结构化**

对于 `@param` 和 `@tparam` 标签，其 `{FirstPieceOfText}` 部分被结构化为：

`{ParameterName} <CalculatedPaddingSpaces2> @ref {ReferencedType}`

其中：

1.  **`{ParameterName}`:** 这是从代码中提取的实际参数或模板参数名称。它紧随 3.3 节计算出的 `<CalculatedPaddingSpaces1>` 之后开始，其起始位置已对齐到“内容版心” (`winyunq.targetCharOffsetTagFirstLineText`)。记录 `{ParameterName}` 的显示长度 `len_ParamName`。

2.  **`<CalculatedPaddingSpaces2>`:** 这是在 `{ParameterName}` 和 `@ref` 关键字之间需要填充的空格。
    *   **计算:**
        *   `@ref` 关键字的目标起始位置（相对于 `{ParameterName}` 的起始位置）是 `winyunq.targetRelativeOffset_AdditionalInfoStart_FromNameDescStart`。
        *   `numSpacesToPad2 = winyunq.targetRelativeOffset_AdditionalInfoStart_FromNameDescStart - len_ParamName`。
        *   应用最小空格约束: 若 `numSpacesToPad2 < winyunq.minSpaces_BetweenNameAndRef`，则 `numSpacesToPad2 = winyunq.minSpaces_BetweenNameAndRef`。
    *   **应用:** 在 `{ParameterName}` 之后填充 `numSpacesToPad2` 个空格。

3.  **`@ref`:** 固定的 Doxygen 关键字，表达的是参数类型。

4.  **`{ReferencedType}`:** 这是需要引用的类型名称。
    *   **类型处理:**
        *   类型名称应尽可能简洁明了。
        *   **对于指针类型 (如 `bool*`, `MyClass*`)，在 `@ref` 后引用时，应去掉末尾的星号 `*`，只引用其基础类型（如 `@ref bool`, `@ref MyClass`）。指针语义应在后续的嵌套 `@details` 中说明。** (这是根据您的要求明确规定)
        *   对于引用类型 (如 `const std::string&`)，通常引用其基础类型 (`@ref std::string`)，并在 `@details` 中说明是常量引用。
        *   对于模板类型 (如 `const std::vector<DataType>&`)，可以引用模板本身 (`@ref std::vector`) 或其模板参数 (`@ref DataType`)，并在 `@details` 中详述。推荐引用基础模板或最相关的类型。
    *   **填充空格:** 在 `@ref` 关键字和 `{ReferencedType}` 之间填充1个空格。

**强制嵌套 `@details`:**

*   对于使用此结构化 `{FirstPieceOfText}` 的 `@param` 和 `@tparam`,`@return`，**必须**在其下一行添加一个嵌套的 (Level 1) `@details` 标签，用于提供该参数的详细描述、用途、约束（如指针是否可空、引用的常量性等）。
*   对于`@return`中，对于返回值的含义枚举使用`@retval`

**规则 E: `@extends` 的 `{FirstPieceOfText}` 结构化**

对于 `@extends` 标签，其 `{FirstPieceOfText}` 部分被结构化为：

`{Visibility} {BaseClassName}`

其中：

1.  **`{Visibility}`:** 继承的可见性 (`public`, `protected`, `private`)。
2.  **`{BaseClassName}`:** 基类的名称。
3.  **空格计算:** `{Visibility}` 紧随 3.3 节计算出的 `<CalculatedPaddingSpaces1>` 之后开始。`{Visibility}` 和 `{BaseClassName}` 之间**必须**有且仅有一个空格。

**示例:**

```cpp
    * @extends     public BaseWidget
    * @extends     private ISerializable
```
