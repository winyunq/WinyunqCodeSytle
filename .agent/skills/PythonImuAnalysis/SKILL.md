---
name: PythonImuAnalysis
description: "Python IMU 数据处理与机器学习规范，强制执行 Winyunq 跨语言统一风格。"
---

# PythonImuAnalysis Skill

## 1. 核心命名规范 (Python Eternal Truths)

> [!IMPORTANT]
> **Python 风格强制对齐 C++ (Winyunq Style)**：
> - **全面 PascalCase**：函数名（`AddDataRecord()`）、变量名（`CurrentStatus`）、类名（`ImuManager`）均必须使用大驼峰。
> - **禁止下划线**：除常量（`SCREAMING_SNAKE_CASE`）外，严禁在任何命名中使用 `_`。
> - **严禁缩写**：必须使用完整语义（如 `Accelerometer` 而非 `Accel`）。
> - **物理空行**：严禁在代码逻辑块与注释之间留空行。

## 2. Python Doxygen 规范

由于 Python 语法限制，我们采用 `##` 引导的块注释来模拟 C++ 的 `/** ... **/`，确保其在 Doxygen 中被正确解析且视觉统一。

### 块注释模板 (Col 15/35 对齐)
```python
##
# @brief       函数说明摘要
# @param       Name: Type       参数说明
# @return      Desc: Type       返回值说明
##
def MyFunction(ParamA, ParamB):
    # 本地上下文注释（使用 Python 原生 #）
    Result = ParamA + ParamB
    return Result
```

## 3. 数据处理战术 (Tactical Standards)

- **硬件调用**：并行计算优先使用 `torch.cuda`（RTX 4060），串行逻辑在 CPU（13900HX）单线程完成。
- **G 值处理**：绝对禁止硬编码 9.81，必须调用项目统一的地理重力模块。
- **数据集**：默认参考数据集路径 `D:\InertialSensingAndAdvancedNavigationLab\IMU-GNSS\mahony_madgwick\data`。

## 4. 自动化集成
- 脚本应能够被 `WinyunqLinter.py` 同步校验。
- 复杂逻辑必须配备 `gui.py` 用于生成配置 `.json`。
