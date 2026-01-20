---
description: C++ 协作开发工作流与 Winyunq 风格规范
---

# C++ Winyunq 协作开发 Skill

本 Skill 定义了 C++ 项目的协作开发流程、权限管理以及编码风格。核心目标是实现 AI 与人类的高效分工：人类制定战略（API/架构），AI 执行战术（实现/细节），并通过严格的“锁定”机制保护核心代码。

## 1. 核心工作流 (The 3-Phase Workflow)

开发遵循严格的三个阶段。AI 必须根据当前所处的阶段采取不同的行动。

### Phase 1: 原型与草稿 (Prototyping)
*   **目标**: 快速生成代码结构，验证思路。
*   **文件特征**: 文件名必须带有 `Gemini_` 前缀 (e.g., `Gemini_MyClass.hpp`, `Gemini_MyClass.cpp`).
*   **权限**: 
    *   **AI**: 拥有完全控制权。**始终覆盖** (Overwrite) 现有的 `Gemini_` 文件，无需犹豫。
    *   **User**: 审查生成结果，提出修改意见。
*   **操作**: 使用 `scripts` 快速生成头文件声明和空的 CPP 实现。

### Phase 2: 接口锁定 (API Locking)
*   **目标**: 确定最终的 API 设计，并生成文档。
*   **文件特征**: 正式文件名 (无前缀)，头文件 (`.hpp`/`.h`) 包含完整的 `/** ... */` 文档注释。
*   **权限**:
    *   **User**: 确认 API 设计，授权将 `Gemini_` 文件转正。
    *   **AI**: 
        *   **禁止修改** 任何带有 `/** ... */` 注释的类、函数声明或枚举，除非获得明确指令（如“重构 API”）。
        *   **只读** 头文件，以此为契据去编写 CPP 实现。
*   **关键动作**: 为所有 Public/Protected 接口添加标准的 `/**` WinyunqDoxygen 块。

### Phase 3: 实现锁定 (Implementation Locking)
*   **目标**: 完成功能实现，并固化逻辑。
*   **文件特征**: 正式文件名，源文件 (`.cpp`) 内部包含详细的 `///` 逻辑注释。
*   **权限**:
    *   **User**: 验收功能，确认逻辑无误。
    *   **AI**: 
        *   **禁止修改** 任何包含密集 `///` 注释的逻辑块。
        *   仅在获得明确授权（如“优化性能”、“修复 Bug”）时方可修改。
*   **关键动作**: 在 CPP 文件中，使用 `///` 对关键逻辑步骤进行注释。

---

## 2. 权限与“锁定”机制 (Locking Mechanism)

### 2.1 锁定状态判定 (State Machine)

脚本将根据**注释的存在性**与**内容**来判断代码段的状态。

| 状态 (Status)     | 判定条件 (Condition)                                                 | 含义 (Meaning)                          | AI 权限 (Permission)                       |
| :---------------- | :------------------------------------------------------------------- | :-------------------------------------- | :----------------------------------------- |
| **错误 (Error)**  | 代码上方 **无** 任何 `///` (声明) 或 `/**` (定义) 注释。             | **风格违规**。代码不符合 Winyunq 规范。 | **必须修复**。AI 应优先补充注释框架。      |
| **草稿 (Draft)**  | 有注释，但 **无** `@brief` 标签；或者 `@brief` 的内容为 `"Gemini"`。 | **未定稿**。接口或实现尚在调整中。      | **可编辑**。AI 可以自由修改代码和注释。    |
| **锁定 (Locked)** | 有注释，且包含有效的 `@brief [非Gemini内容]`。                       | **已定稿**。用户已确认设计/实现。       | **只读**。除非获得显式授权，否则禁止修改。 |

### 2.2 文件级权限
*   **Gemini 前缀**: 文件名以 `Gemini_` 开头 (e.g., `Gemini_Data.hpp`) -> **全局草稿**，无论内部注释如何，均视为可被覆盖 (Overwrite)。
*   **移除前缀**: 当用户对 `Gemini_` 文件内容满意时，脚本可将其重命名为正式文件 (移除前缀)。此时内部的代码将受上述 **2.1 锁定状态** 的管辖。

### 2.3 匹配规则
*   **头文件 (.hpp/.h) - 定义与文档**:
    *   对于 **类/结构/枚举/命名空间** 的定义 (`{}`块)，检查上方紧邻的 `/** ... */`。
    *   **判定**: 若存在 `/**` 且 `@brief` 内容不含 "Gemini"，视为 **Locked**。
*   **源文件 (.cpp) - 实现**:
    *   对于 **函数实现** (`{}`块)，检查上方紧邻的 `///` 行。
    *   **判定**: 若存在 `/// @brief` 且内容不含 "Gemini"，视为 **Locked**。
    *   **注意**: CPP 中**不使用** `/**` 进行锁定判定。即使是函数定义，在 CPP 中也仅需单行 `///` 即可锁定。

---

## 3. 编码风格 (Winyunq Style)

### 3.1 文件分工
*   **头文件 (.hpp)**: **文档中心**。存放所有的类、结构体、枚举定义及函数声明。使用 `/** ... */` 块进行详细文档化。
*   **源文件 (.cpp)**: **逻辑中心**。存放具体实现。使用 `///` 进行行级注释，解释“怎么做 (How)”。

### 3.2 命名规范
*   **Types (类/结构/枚举)**: `UpperCamelCase` (e.g., `DataProcessor`, `NetworkManager`)
*   **Functions & Variables**: `lowerCamelCase` (e.g., `processData`, `userIndex`)
*   **Constants & Enum Values**: `SCREAMING_SNAKE_CASE` (e.g., `MAX_RETRY_COUNT`, `STATUS_IDLE`)
*   **Template Params**: `UpperCamelCase`，禁止单字母 (e.g., `ValueType`, `IteratorType`)

### 3.3 注释规范 (核心)

#### 头文件 (.hpp) - 必须使用 `/** ... */`
所有主要的定义（Class, Struct, Method Declaration）必须配备标准 WinyunqDoxygen 块。
*   **格式**:
    *   `@brief`: 简述 (必选)
    *   `@param`: 参数说明 (对齐 Col 15 / Col 35)
    *   `@return`: 返回值说明 (对齐 Col 35)
*   **示例**:
    ```cpp
    /**
     * @brief       计算复杂的数学运算
     * 
     * @param       参数名称: inputValue                    数据类型:        double
     * @param       参数名称: mode                          数据类型:        int
     * 
     * @return      计算结果                                数据类型:        double
     **/
    double calculateResult(double inputValue, int mode);
    ```

#### 源文件 (.cpp) - 必须使用 `///`
函数体内部的逻辑解释使用 `///`。**禁止**在函数体内部使用 `/**`。
*   **原则**: 每 2-3 行逻辑代码至少应该有一行 `///` 注释。
*   **格式**: `///` 后接空格，与代码同缩进。
*   **示例**:
    ```cpp
    double calculateResult(double inputValue, int mode)
    {
        /// 检查输入是否有效
        if (inputValue < 0) return 0.0;

        /// 根据模式应用系数
        double factor = (mode == 1) ? 2.5 : 1.0;
        
        /// 返回最终计算值
        return inputValue * factor;
    }
    ```

---

## 4. 脚本工具 (Automation Tools)

> **CRITICAL**: You MUST use these tools for all code modifications. Do not use generic file tools.

- **SetTarget.py**: 上下文管理 (Call First)。
- **CheckStyle.py**: 状态检查 (Check) 与 晋升 (Promote)。
- **WriteCode.py**: 唯一允许的代码写入工具 (支持 Declare/Define/Enable/Disable)。
- **ReadCode.py**: 代码读取 (Declaration/Definition/Reference)。
- **AutomaticDocument.py**: 文档生成与格式化 (Format)。
