# Winyunq Doxygen Block 格式指南 (Winyunq Style)

## 1. 文档目的与范围

本文档**唯一且专门地**描述了 Winyunq C++ 协作编程风格中 **WinyunqDoxygen Block** (`/** ... **/` 块注释) 的**内部视觉格式和构建规则**。

**核心目标：** 针对**WinyunqDoxygen Block** (`/** ... **/` 块注释)，定义如何通过精确计算和填充**空格**，将 `@tag` 命令及其关联文本排版成符合 Winyunq 风格的、具有高信息密度和可扫描性的结构化文档块。**亦可理解为代码中的readme.md**

**核心隐喻：** 将 Winyunq DocBlock 视为一个**基础的 Markdown 文本流**，其中 `@tag` 命令是引入特定行内排版规则的特殊指令，类似于 Markdown 中的标题或列表项对其后第一行内容的影响。而真正的核心是**WinyunqDoxygen Block** (`/** ... **/` 块注释)是**readme.md**

**范围限制：** 本文档**不讨论**何时使用 WinyunqDoxygen Block 或选择哪些 `@tag`。它只关注**如何格式化**一个给定的块内容。

**与 Doxygen 的关系：** 使用 Doxygen 兼容标签，但格式规则优先。

## 2. Winyunq DocBlock 的基本构成与边界

1.  **起始标记:** `/**` (顶格，不参与外部代码缩进)。
2.  **内容行:** 每行以 ` * ` (标准的`/** ... **/` 块注释) 开始。
3.  **结束标记:** `**/` (标准的`/** ... **/` 块注释)。

```cpp
/**
 *
 *
 **/
```
*   **目的:** `/**` 和 `**/` 顶格界定块范围。` * ` 是每一内容行的固定前缀，其后的所有内容都基于此起点进行排版。AI你需要自行注意：`/** ... **/` 块注释中的`**/`很容易被识别为加粗，如果阅读时有疑惑需要思考是否是两个星号被转译了。

## 3. 核心排版规则：Markdown 基础与 `@tag` 特殊行处理 (强制)

本节定义了内部内容的精确排版。所有定位和对齐**必须**通过计算并填充**空格**实现。**禁止**使用 `Tab`。

### 3.1 默认文本流：Markdown 行为 (强制)

*   **基础定位:** 在 Winyunq DocBlock 内部，所有**纯描述性文本**（即不属于 `@tag` 命令本身的部分）的第一个字符，**必须**紧随其所在行的行起始符 ` * ` 之后开始（即从该行的**第 3 个字符位置**开始）。即正常**不参与缩进**的换行。
    *   格式: ` * TextFlowsNaturallyFromHere`
*   **换行即新行:** 当文本内容需要换行时（无论是 `@tag` 后的描述文本还是独立的纯文本段落），**新的一行总是重新从默认的文本起始位置（紧随 `* `）开始**。不存在基于前一行的“继承式缩进”。
    *   **可以理解为：** 每一个 ` * ` 之后都是一个新的 Markdown 行的开始。
*   **Markdown 语法兼容:** 允许并推荐在纯文本中使用标准 Markdown 标记（如强调、列表、链接）和 LaTeX 公式。这些标记应自然地嵌入从第 3 字符位置开始的文本流中。
*   **句子换行建议:** 为保持可读性，推荐在句子结束标志（如 `.`,`。`）后进行文本换行。
*   **效果:** 这是块内文本最自然、最基础的左对齐流，完全符合 Markdown 的行行为。
*   **注意:**正因为将**WinyunqDoxygen Block** (`/** ... **/` 块注释)视为**写在代码中的readme.md**，所以**WinyunqDoxygen Block** (`/** ... **/` 块注释)**绝不缩进**

### 3.2 `@tag` (信息标记)：Markdown 流中的特殊指令与层级定位

`@tag` 命令是 Doxygen 引入的、用于标记特定语义信息的特殊指令。在 Winyunq 风格中，我们将 `@tag` 视为对基础 Markdown 文本流的一种**结构化标记**，其定位规则模拟了 Markdown 嵌套列表的视觉层级感。

**`@tag` 的核心行为与定位规则 (强制):**

1.  **`@tag` 定义:**  `@tag` 类似于 Markdown 的列表项标记或标题标记，它标志着一个新的结构化信息单元的开始。因此，`@tag`存在层级，**每个层级相差一个空格**（非缩进。仅仅是类似于首行空格）。
2.  **层级示例:** `@tag` 的逻辑层级（由主《WinyunqStyleGuide.md》根据语义定义）通过其 `@` 符号相对于行起始符 `* ` 的**固定前导空格数**在视觉上体现。这**仅定位 `@` 符号本身**。
    *   **一级 `@tag` (Level 0):** ` * ` + **0 前导空格** + `@tag` (`@` 在第 3 字符位置，无空格)
        *   格式: `* @tag`
    *   **二级 `@tag` (Level 1):** ` * ` + **1 前导空格** + `@tag` (`@` 在第 4 字符位置，1空格)
        *   格式: `*  @tag`
    *   **三级 `@tag` (Level 2):** ` * ` + **2 前导空格** + `@tag` (`@` 在第 5 字符位置，2空格)
        *   格式: `*   @tag`
    *   **AI 实现提示:** 当接收到生成某个层级 `@tag` 的指令时，必须精确地在 ` * ` 后插入对应数量 (0, 1, 或 2) 的空格，然后再附加 `@` 和标签关键字。

3.  **`@tag` 不影响后续行的默认文本流:** `@tag` 的层级定位**仅作用于 `@tag` 关键字本身**。它**不会**改变后续文本行，作为markdown内容，仅仅补充空格，不存在“行内缩进”

**目的 (Purpose):** 将 `@tag` 定义为 Markdown 流中的特殊结构标记，其层级通过精确的前导空格（而非传统缩进）表示，同时明确其定位仅影响自身，不干扰后续行的基础排版。这为后续定义 `@tag` 行内文本的特殊排版奠定了基础。

### 3.3 `@tag` 行基础结构与首段文本对齐

所有包含 `@tag` 命令的行，其基础结构可以抽象地表示为：

`@[TagMarkerString]<CalculatedPaddingSpaces>{FirstPieceOfText}`

其中：

1.  **`[TagMarkerString]` (标签标记部分):**
    *   **构成:** 由Doxygen命令 `@` 符号后的具体的 Doxygen 命令关键字 (如 `brief`, `param`) 组成。
    *   **示例:** `brief`, `details`, `note`。
    *   **长度:** 在计算填充空格时，需要获取 `[TagMarkerString]` 的实际显示长度（以字符计），记为 `lengthTagMarker`。

2.  **`<CalculatedPaddingSpaces>` (填充空格部分):**
    *   **目的:** 用于将紧随其后的 `{FirstPieceOfText}` 的起始位置精确对齐到 Winyunq 定义的“内容版心”。
    *   **计算规则 (强制):**
        *   **核心布局参数:**
            *   `winyunq.targetCharOffsetTagFirstLineText = 15` (目标字符偏移量，从行首第 1 个字符计)
            *   `winyunq.minSpacesAfterTagKeyword = 1` (最小空格数)
        *   **计算公式:**
            1.  `numSpacesToPad = winyunq.targetCharOffsetTagFirstLineText - lengthTagMarker`
            2.  若 `numSpacesToPad < winyunq.minSpacesAfterTagKeyword`，则 `numSpacesToPad = winyunq.minSpacesAfterTagKeyword`。
        *   **应用:** 在 `TagMarkerString` 之后，**必须**填充 `numSpacesToPad` 个空格。

3.  **`{FirstPieceOfText}` (首段核心文本部分):**
    *   **内容:** 这是与 `@tag` 直接关联的核心文本内容。
        *   对于普通 `@tag` (如 `@details`, `@note`)，它是该标签的描述文本。
        *   对于 `@param`,`@tparam`,`@return`，它是 `{ParameterName} <CalculatedPaddingSpaces2> @ref {ReferencedType}`整体。
        *   对于 `@extends`，它是 `"{visibility} {baseClassName}"`。
    *   **定位:** 其第一个字符紧随 `<CalculatedPaddingSpaces>` 之后，起始于从行首计的第 `winyunq.targetCharOffsetTagFirstLineText` 个字符位置（即对齐到特定行个字符）。
    *   **后续行处理:** `@tag`仅仅是特殊的markdown语法，**不含缩进**,如果 `{FirstPieceOfText}` 或其后的描述需要换行，所有后续文本行严格遵循 **3.1 节的默认文本流定位**（从第 3 字符位置开始）。


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


### 3.5 后续文本行处理 (严格遵循默认文本流)

*   **规则:** 再次强调**WinyunqDoxygen Block** (`/** ... **/` 块注释)是写在代码里面的readme.md文件，因此`@tag`是自定义的markdown规则，因此如果 `@tag` 后的描述文本（或其嵌套的 `@details` 等的文本）需要换行，则换行后的文本会因为是markdown中的文本默认处理，即`@tag`仅仅是涉及补充空格，**不影响文本**
*   **效果:** `@tag` 命令仅影响其所在行的特殊排版。所有后续的文本行都回归到最基础的 Markdown 行行为。

## 4. 黄金标准示例 (格式演示 - 更新以匹配新规则 v2.6)
```cpp
/**
 * @class       ComplexDataProcessor
 * @brief       一个用于演示所有格式规则的复杂数据处理器
 * @extends     public BaseProcessor               
 * @extends     private ILoggable                  
 *  @details     此类旨在全面展示 Winyunq DocBlock 的排版特性。
 * 它结合了模板、多参数、多层级标签以及需要换行的长描述文本。
 * 注意观察所有对齐点是如何通过计算空格实现的。
 *   @note        这是一个纯粹用于格式演示的类，不包含实际逻辑。
 *   @warning     请勿在生产代码中直接使用此类。
 *
 * @tparam      ElementType                     @ref BaseItem           // 应用规则 D
 *  @details     容器将存储的元素类型，必须派生自 BaseItem。
 * @tparam      AllocatorType                   @ref std::allocator     // 应用规则 D
 *  @details     用于容器内存管理的分配器类型。
 *
 * @param       inputData                       @ref const std::vector // 应用规则 D (引用基础模板)
 *  @details     输入的待处理数据向量 (元素类型为 ElementType)。向量不能为空。
 * @param       processorConfig                 @ref const Config   // 应用规则 D (引用基础类型)
 *  @details     处理器的配置对象（常量引用），用于控制内部算法。
 *   @note        如果 processorConfig.isValid() 返回 false，则处理可能失败。
 * @param       outExecutionStatus              @ref bool              // 应用规则 D (指针类型去掉了 *)
 *  @details     用于返回操作执行状态的输出参数（指针）。如果操作成功，将被设置为 true，否则为 false。调用者必须提供有效的 bool 指针。
 *
 * @return      处理结果的聚合值                 @ref ElementType       // 应用规则 F (带类型引用)
 *  @details     返回所有输入数据经过处理后的最终聚合结果。具体的聚合方式取决于 processorConfig 中的 mode 设置。
 *  @retval      static_cast<ElementType>(0) 如果输入数据为空或配置无效。
 *  @retval      计算出的聚合值              如果处理成功。
**/
```
## 5. 结语

本《Winyunq Doxygen Block 格式指南》提供了构建符合 Winyunq 风格的 `/** ... **/` 注释块所需的全部格式化规则。AI 代码生成器和开发者在生成或编写此类注释块时，**必须严格遵循**本文档中定义的规则，特别是将块内文本流视为 Markdown 基础，并对 `@tag` 行应用特定的、通过计算空格实现的排版处理。
1.  **Markdown 为绝对基础：** 整个 `/** ... **/` 块首先被视为一个 Markdown 片段，作为写在代码中的readme.md。其内部文本的默认行为（换行、流动）完全遵循 Markdown 的直觉。**因此无论如何不存在缩进，始终置顶**
2.  **`@tag` 是 Markdown 的“行级指令”或“特殊格式化标记”：** 它只影响其所在行以及紧随其后的第一行文本的特殊排版。不存在所谓的`@tag`行内换行，因为`@tag`本身仅仅是换行首行的存在
3.  **后续行自然回归：** 所有后续文本行自然地回归到 Markdown 的标准文本流（紧随 ` * `）。**无论如何，不存在缩进**
4.  **“核心布局参数”仅在需要进行特殊排版计算时引入和定义。**
5.  **移除示例中的所有 `//` 解释性注释**，让格式本身说话。
6.  **强调相对计算和逐步构建。**

