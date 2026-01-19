---
name: WinyunqCore
description: "Winyunq 项目核心规范，定义战略、战术、代码风格及工程自动化流程。"
---

# WinyunqCore Skill

## 1. 核心原则 (Core Principles)

### 协作边界 (Strategic vs. Tactical)
- **战略由人**：开发者负责架构设计、模块划分、命名规范等核心决策。
- **战术由 AI**：AI 负责代码实现、细节优化、Bug 修复及性能调优。
- **扩产优先 (Maximize Output Efficiency)**：使用相同的 Token/上下文空间，通过结构化（Winyunq Style）产出更高信息密度的代码与文档。

### 临时文件规则 (Gemini Prefix)
- **Gemini 前缀**：所有实验性质的文件必须带有 `Gemini` 前缀。
- **沙盒机制**：实验成功后需由用户确认才可去掉前缀，正式文件严禁使用 V1, V2 等后缀。

## 2. 核心命名规范 (The Eternal Truths)

> [!IMPORTANT]
> **代码风格“永恒真理”**：
> - **PascalCase (大驼峰)**：所有文件夹、文件、类、函数、变量必须使用大驼峰命名。
> - **完整命名 (Full Naming)**：严禁缩写（如使用 `Accelerometer` 而非 `Accel`）。
> - **无下划线 (No Underscores)**：禁止在任何命名中使用 `_`。
> - **强制对齐**：块注释 `/** ... **/` 必须严格遵守 Col 3/15/35 基准对齐。

### 3. 代码锚定与锁定 (Anchoring & Locking)
- **正式注释锁定原则 (Formal Comment = Locked)**：
    - **锁定区**：凡是拥有 Winyunq 标准块注释（C++ 为 `/**`，Python 为 `##`）的代码块，视为“已确定的真理”。AI 默认禁止擅自修改锁定的逻辑。
    - **实验区**：带有 `Experimental` 标签或仅有简略注释的代码。AI 可自由覆盖、重构并改进其逻辑。
- **普通区域**：AI 根据需求读写，但应尊重已建立的锚定边界。

### 阶段一：协议先行 (Header First)
- 开发者与 AI 协商确定头文件（`.hpp`）及函数列表。
- AI 在头文件中预填充符合规范的 `/** ... **/` 块注释。

### 阶段二：骨架锚定 (Implementation Anchoring)
- 实现函数时，AI 应在 `.cpp` 中通过注释或工具锚定函数边界，在限定范围内填充逻辑，避免破坏架构。

### 阶段三：自动化质量监控 (Linting & Refreshing)
- AI 定期运行 Skill 内置脚本（见 `scripts/`），统计并修复格式违规点。

## 4. 工具集成 (Skill-MCP Synergy)
- **Skill 是大脑**：存储真理与流程逻辑。
- **Scripts 是手脚**：Skill 下的 `scripts/` 存放专用 Python 脚本。
- **核心工具**：
    - `WinyunqCommenter`: 自动化生成 Col 对齐注释。
    - `WinyunqLinter`: 自动检测并刷新格式（命名、空行、下划线）。
