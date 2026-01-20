---
description: Python 协作开发工作流与 Winyunq 风格规范
---

# Python Winyunq 协作开发 Skill

本 Skill 定义了 Python 项目的协作开发流程、权限管理以及编码风格。

## 1. 核心工作流 (The 3-Phase Workflow)

### Phase 1: 原型与草稿 (Prototyping)
*   **文件特征**: `Gemini_` 前缀 (e.g., `Gemini_data_loader.py`).
*   **权限**: 
    *   **AI**: 拥有完全控制权，可覆盖 (Overwrite)。
    *   **User**: 审查设计。
*   **操作**: 使用 `SetTarget` 快速生成 `.py` 文件骨架。

### Phase 2: 接口锁定 (API Locking)
*   **目标**: 确定 Class 和 Function 的签名。
*   **文件特征**: 正式文件名，Class/Function 下方包含完整的 `"""` 文档字符串 (Docstring)。
*   **权限**:
    *   **锁定标志**: `"""` 文档字符串存在，且内容**不含** "Gemini"。
    *   **AI**: 禁止修改函数签名和文档可。

### Phase 3: 实现锁定 (Implementation Locking)
*   **目标**: 完成内部逻辑。
*   **文件特征**: 正式文件名，代码行上方包含 `#` 注释。
*   **权限**:
    *   **锁定标志**: `#` 注释存在，且内容**不含** "Gemini"。
    *   **AI**: 禁止修改被 `#` 注释保护的逻辑代码块。

---

## 2. 编码风格 (Winyunq Style)

### 2.1 命名规范 (PEP8 + 强制)
*   **Class**: `UpperCamelCase` (e.g., `DataManager`).
*   **Function/Variable**: `lower_snake_case` (e.g., `load_data`, `user_id`).
*   **Constant**: `SCREAMING_SNAKE_CASE` (e.g., `MAX_RETRY`).
*   **File**: `lower_snake_case` (e.g., `data_manager.py`).

### 2.2 注释与锁定规范

#### API 文档 (Docstring) - 对应 C++ `/**`
每个 Class 和 Function 必须有文档字符串。
*   **锁定**: `""" ... """` 意味着 API 已定稿。
*   **格式**: Google Style 或 NumPy Style 均可，必须清晰描述 Args 和 Returns。
    ```python
    class DataProcessor:
        """
        核心数据处理类 [LOCKED]
        
        Args:
            capacity (int): 初始容量
        """
        def process(self, data):
            """
            处理输入数据 [LOCKED]
            
            Args:
                data (list): 输入列表
            Returns:
                bool: 处理成功状态
            """
            pass
    ```

#### 实现注释 (Hash Comment) - 对应 C++ `///`
关键逻辑步骤必须使用 `#` 注释。
*   **锁定**: `#` 意味着该行/该块逻辑已定稿。
*   **格式**: `#` 后接空格，位于代码上方。
    ```python
    def calculate(x):
        # 检查边界条件 [LOCKED]
        if x < 0:
            return 0
            
        # 应用核心公式 [LOCKED]
        result = x * 2.5
        return result
    ```

---

## 3. 脚本工具 (Automation Tools)

> **CRITICAL**: You MUST use these tools for all code modifications. Do not use generic file tools.

- **SetTarget.py**: 上下文管理 (Call First)。
- **CheckStyle.py**: 状态检查 (Check) 与 晋升 (Promote)。
- **WriteCode.py**: 唯一允许的代码写入工具 (支持 Declare/Define/Enable/Disable)。
- **ReadCode.py**: 代码读取 (Declaration/Definition/Reference)。
- **AutomaticDocument.py**: 文档生成与格式化 (Format)。
