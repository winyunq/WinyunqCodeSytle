# Winyunq Doxygen Block 格式指南 (Winyunq Style)

## 1. 文档目的与范围

本文档**唯一且专门地**描述了 Winyunq C++ 协作编程风格中 **WinyunqDoxygen Block** (`/** ... **/` 块注释) 的**内部视觉格式和构建规则**。

**核心目标：** 针对**WinyunqDoxygen Block** (`/** ... **/` 块注释)，定义如何通过精确计算和填充**空格**，将 `@tag` 命令及其关联文本排版成符合 Winyunq 风格的、具有高信息密度和可扫描性的结构化文档块。**亦可理解为代码中的readme.md**

**核心隐喻：** 将 Winyunq DocBlock 视为一个**基础的 Markdown 文本流**，其中 `@tag` 命令是引入特定行内排版规则的特殊指令，类似于 Markdown 中的标题或列表项对其后第一行内容的影响。而真正的核心是**WinyunqDoxygen Block** (`/** ... **/` 块注释)是**readme.md**

**范围限制：** 本文档**不讨论**何时使用 WinyunqDoxygen Block 或选择哪些 `@tag`。它只关注**如何格式化**一个给定的块内容。

**与 Doxygen 的关系：** 使用 Doxygen 兼容标签，但格式规则优先。

## 2. Winyunq DocBlock 的基础形态与 T0 基准

本章详细描述 WinyunqDoxygen Block 的基本构成元素、其在代码文件中的绝对定位，以及在不包含任何特殊 `@tag` 命令时，其内部内容的默认排版规则——即 **T0 基准 (T0 Baseline)** 或 **默认文档流**。

### 2.1 块的边界标记

1.  **起始标记:** `/**`
    *   **定位：** 必须位于其所在物理代码行的**第1列**（顶格）。
    *   **原则：** **绝不参与**其所注释的 C++ 代码元素的任何外部缩进。此为“清除一切左侧缩进”的体现。
2.  **结束标记:** `**/`
    *   **定位：** 必须位于其所在物理代码行的**第1列**（顶格）。
    *   **原则：** 同起始标记，绝不参与外部代码缩进。

### 2.2 内容行的固定前缀

*   在 `/**` 和 `**/` 标记之间的每一个实际内容行，都必须以 ` * ` (一个星号，后跟一个空格) 作为其固定前缀。
*   **列定位：**
    *   星号 `*`：位于该物理行的**第2列**。
    *   星号后的空格：位于该物理行的**第3列**。
*   这个 ` * ` 前缀是每行内容的视觉边界和结构基础。

### 2.3 T0 基准下的默认文档流 (纯 Markdown 内容)

当 WinyunqDoxygen Block 仅包含纯描述性文本时（即没有 `@tag` 命令），其内部内容遵循 T0 基准，表现为一个标准的 Markdown 文档流。

1.  **内容起始点 (T0 Content Origin):**
    *   所有纯描述文本的第一个字符，**必须**紧随其所在行的 ` * ` 前缀之后开始。
    *   **精确列定位：** 这意味着每一行纯描述文本的**第一个有效字符都位于该物理行的第4列**。
2.  **换行规则:**
    *   当描述文本需要换行时，新的一行同样遵循上述规则，其第一个字符也从第4列的 T0 Content Origin 开始。
    *   **不存在**基于前一行的“继承式缩进”。
3.  **Markdown 语法兼容:**
    *   允许并推荐在遵循 T0 Content Origin 的前提下，在纯文本描述中使用标准的 Markdown 语法（如段落、列表、强调、代码片段等）。Markdown 自身的缩进规则（如列表项下的段落缩进）是相对于 T0 Content Origin 计算的。

**表格：DocBlock 结构与 T0 默认文档流的逻辑关系**

| 代码环境外部缩进状态  | Winyunq DocBlock 结构元素 (物理列位置) | 内部有效内容区域 (T0 Content Origin)  |
| :------------------- | :----------------------------------- | :------------------------------------ |
| **Clean** (无视外部) | `/**` (第1列)                        | (边界标记，无直接内容)                |
| **Clean** (无视外部) | ` * ` (`*`在2列, ` `在3列)          | **第4列开始** (Markdown 流的第一行) |
| **Clean** (无视外部) | ` * ` (`*`在2列, ` `在3列)          | **第4列开始** (Markdown 流的中间N行)|
| **Clean** (无视外部) | ` * ` (`*`在2列, ` `在3列)          | **第4列开始** (Markdown 流的最后一行)|
| **Clean** (无视外部) | `**/` (第1列)                        | (边界标记，无直接内容)                |

正如在markdown中，可以按照`,`,`.`,`，`,`。`换行，因此，对于Markdown注释中，换行依据同样也是如此。

**示例：纯 Markdown 内容的 Winyunq DocBlock**

```cpp
/**
 * This is the first line of a pure Markdown description.
 * Its content, like this 'I', starts at column 4.
 *
 * We can include:
 * - Unordered list item 1.
 *   - Nested list item 1.1 (Markdown's own indent from col 4).
 * - Unordered list item 2.
 *
 * And paragraphs, separated by a blank line (which would also
 * just contain " * " if not entirely empty).
 * `inline code` and **bold text** are also fine.
 */
```

## 3. `@tag` 命令的排版：在 T0 基准上的局部变换

本章我们开始讨论包含 `@tag` 命令的行的排版。如第二章所述，Winyunq DocBlock 的每一内容行都以 ` * ` (星号在第2列，空格在第3列) 作为固定前缀，其后的**“内部有效内容区域”**（我们称为 **T0 Content Origin**）从**第4列**开始。

本章的所有讨论和列号计算，都默认是针对这个**从第4列开始的“内部有效内容区域”**。

### 3.1 `@tag` 命令与描述文本的初步行化处理 (遵循 T0)

当一个 `@tag` 命令（例如 `@details`, `@brief`, `@note`）后跟随一段较长的描述文本时，这段长文本需要被分割到多个物理行上，以保证可读性和遵循合理的行长度。

1.  **逻辑视为一体，按 Markdown 原则断行：**
    *   `@tag` 命令及其全部逻辑描述文本（直到下一个同级 `@tag` 或块结束）首先被视为一个连续的文本流。
    *   然后，根据句子结束符 (`.`, `。`)、主要逻辑停顿点 (`,`, `，`)、Markdown 结构元素（标题、列表、代码块、段落分隔）或行长度考虑，将此文本流分割成多个物理行。

2.  **初步行化后的 T0 应用：**
    *   经过上述断行处理后，每一条新产生的物理行，其内容都将填充到从**第4列开始的“内部有效内容区域”**。

**表格：`@tag` 及其长描述文本在“内部有效内容区域”(第4列起)的初步布局**

假设 `@tag` 的逻辑内容是：
`@details This is sentence one. This is sentence two, which is a bit longer. And this is sentence three.`

**在“内部有效内容区域”（从第4列开始）的呈现：**
*(每一行都隐含了第二章定义的 ` * ` 前缀)*

| “内部有效内容区域” (从第4列开始) 的内容片段                                      |
| :--------------------------------------------------------------------------------- |
| `@details This is sentence one.`                                                   |
| `This is sentence two, which is a bit longer.`                                     |
| `And this is sentence three.`                                                      |

**示例（完整 DocBlock 片段）：**
```cpp
/**
 * @details This is the first sentence of a detailed description.
 * This is the second sentence, which might explain more about
 * the previous point or introduce a new aspect.
 *   - This could be a list item starting on a new line.
 *   - Another list item.
 * And this is a concluding sentence for the details.
 */
```
**解读：**
*   在第一行，`@details This is...` 中的 `@` 符号位于物理行的第4列。
*   在第二行，`This is the second...` 中的 `T` 符号位于物理行的第4列。
*   以此类推，所有因断行产生的新行，其内容都始于物理行的第4列。

## 3. `@tag` 命令及其描述文本的排版

本章我们开始讨论包含 `@tag` 命令的行的排版。如第二章所述，所有 Winyunq DocBlock 的内容行都以 ` * ` (星号在第2列，空格在第3列) 作为前缀，其后的有效内容区域（**T0 Content Origin**）从**第4列**开始。

### 3.1 `@tag` 命令与描述文本的初步行化处理

当一个 `@tag` 命令（例如 `@details`, `@brief`, `@note`）后跟随一段较长的描述文本时，为了保持代码的可读性和遵循合理的行长度限制，这段长文本需要被分割到多个物理行上。

**核心原则：将 `@tag` 及其全部逻辑描述视为一个连续的文本流，然后根据 Markdown 的可读性原则进行断行。**

1.  **逻辑上的连续性：**
    *   在概念上，`@tag` 命令及其所有的描述文本（直到遇到下一个同级 `@tag` 或块结束）构成一个单一的逻辑单元。
    *   例如：`@details This is a very long description that continues for many sentences, possibly including Markdown formatting like lists or code blocks.`

2.  **断行依据 (Markdown 可读性原则)：**
    *   **句子结束符：** 强烈建议在完整的句子结束标志（如英文句号 `.`, 中文句号 `。`）之后进行换行。
    *   **主要从句或短语分隔符：** 也可以在逗号 (`,`, `，`)、分号 (`;`, `；`) 等表示逻辑停顿的地方考虑换行，如果这有助于提高可读性。
    *   **Markdown 结构元素：**
        *   Markdown 标题（`### Title`）之后通常是新的一行。
        *   列表项 (`- Item`, `1. Item`) 通常各自占据新行。
        *   代码块 (```cpp ... ```) 的开始和结束标记以及其内部的每一行代码，自然形成多行。
        *   段落之间由一个或多个空行（在 DocBlock 中即只包含 ` * ` 的行或完全空白的 ` *` 行）分隔，每个段落的第一行是新行。
    *   **行长度限制：** 虽然 Winyunq 风格不强制规定严格的字符数行长度，但应避免出现过长的单行文本，以方便在标准编辑器中阅读。通常，保持行长在 80-120 字符范围内是一个良好的实践。

3.  **初步行化后的 T0 应用：**
    *   经过上述断行处理后，每一条新产生的物理行，都将遵循第二章定义的 T0 基准：
        *   以 ` * ` (星号在第2列，空格在第3列) 作为前缀。
        *   该行上的**所有内容**（包括 `@tag` 命令本身，或其描述文本的片段）都从**第4列 (T0 Content Origin)** 开始。

**表格：`@tag` 及其长描述文本的“初步行化”与 T0 布局**

假设我们有以下逻辑内容：
`@details This is sentence one. This is sentence two, which is a bit longer. And this is sentence three.`

**初步行化处理 (例如在每个句子后换行)，并应用 T0 布局：**

| 逻辑顺序 | Winyunq DocBlock 行前缀 (`*`@2,` `@3) | “内部有效内容区域” (从第4列开始) 的内容片段                                      |
| :------- | :--------------------------------------- | :--------------------------------------------------------------------------------- |
| 第1行    | ` * `                                    | `@details This is sentence one.`                                                   |
| 第2行    | ` * `                                    | `This is sentence two, which is a bit longer.`                                     |
| 第3行    | ` * `                                    | `And this is sentence three.`                                                      |

**示例：`@details` 的初步行化**

```cpp
/**
 * @details This is the first sentence of a detailed description.
 * This is the second sentence, which might explain more about
 * the previous point or introduce a new aspect.
 *   - This could be a list item starting on a new line.
 *   - Another list item.
 * And this is a concluding sentence for the details.
 */
```

### 3.2 针对 `@tag` 命令行的布局优化：T1 变换 (层级缩进)

正如同“首行空两格”，**针对于@tag首行内容**，我们需要实现对应的效果。

**3.2.1 T1变换规则：在“Markdown内容区”起始处，针对@tag所在行添加层级空格**

*   T1变换**仅作用于**那些实际包含 `@tag` 命令的物理行。
*   它通过在该行“Markdown内容区”的起始处（即物理行第4列的位置）预置一定数量的空格，来调整 `@` 符号的相对起始位置。
*   **逻辑层级数 (0-indexed) 与 T1空格数：**
    *   一级`@tag` (L0): 在“Markdown内容区”起始处插入 **0** 个层级空格。
    *   二级`@tag` (L1): 在“Markdown内容区”起始处插入 **1** 个层级空格。
    *   N+1级`@tag` (LN): 在“Markdown内容区”起始处插入 **N** 个层级空格。

**3.2.2 表格：T1变换对“Markdown内容区”布局的影响**

下表聚焦于**“Markdown内容区”（从物理行第4列开始）**，展示T1变换如何通过在该区域起始处添加空格，来改变 `@tag` 命令的相对布局。

| @tag内容逻辑顺序 |T1|内容片段                                      |
| :------- | :--------------------------------------- | :--------------------------------------------------------------------------------- |
| 第1行    | N个空格 | `@details This is sentence one.`                                                   |
| 第2行    | **Clean** (无空格)           | `This is sentence two, which is a bit longer.`                                     |
| 第3行    | **Clean** (无空格)               | `And this is sentence three.`                                                      |

**解读表格：**
*   **第一行 (“T1层级前导空格”)：**只有开始于`@`的行，需要补充N个空格。触发条件为本行开始于`@`
*   **其他行(“实际呈现的文本内容”)：**其他行清除所有缩进，补充空格与`@`无关。

**示例（回顾）：**
```cpp
/**
 *  @details This is the L1 @details. '@' is at col 5.
 * This is its second line. 'T' is at col 4.
 *   @note This is an L2 @note. '@' is at col 6. (2 space)
 * This is the L1 note's second line. 'T' is at col 4.
 */
```
*  只有开始于`@`的行，需要在`@`左边插入N个空格。**仅仅是开始于`@`的行，仅仅是此行左边**

## 5. 结语

本《Winyunq Doxygen Block 格式指南》提供了构建符合 Winyunq 风格的 `/** ... **/` 注释块所需的全部格式化规则。AI 代码生成器和开发者在生成或编写此类注释块时，**必须严格遵循**本文档中定义的规则，特别是将块内文本流视为 Markdown 基础，并对 `@tag` 行应用特定的、通过计算空格实现的排版处理。
1.  **Markdown 为绝对基础：** 整个 `/** ... **/` 块首先被视为一个 Markdown 片段，作为写在代码中的readme.md。其内部文本的默认行为（换行、流动）完全遵循 Markdown 的直觉。**因此无论如何不存在缩进，始终置顶**
2.  **`@tag` 是 Markdown 的“行级指令”或“特殊格式化标记”：** 它只影响其所在行以及紧随其后的第一行文本的特殊排版。不存在所谓的`@tag`行内换行，因为`@tag`本身仅仅是换行首行的存在
3.  **后续行自然回归：** 所有后续文本行自然地回归到 Markdown 的标准文本流（紧随 ` * `）。**无论如何，不存在缩进**
4.  **“核心布局参数”仅在需要进行特殊排版计算时引入和定义。**
5.  **移除示例中的所有 `//` 解释性注释**，让格式本身说话。
6.  **强调相对计算和逐步构建。**

