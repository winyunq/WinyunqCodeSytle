# UE5 MCP 战术操作指南 (Winyunq V5)

## 1. 核心战术流：声明->实现 迭代流
在 Winyunq 架构中，代码编写被分为两个严格阶段：**声明阶段**与**定义阶段**。

### A. 声明阶段 (Declare Action)
- **目的**: 确定类结构、API 协议与 Doxygen 文档。
- **操作**: 使用 `Declare` 命令输入 JSON 协议。
- **效果**:
    - 自动生成/更新 `.hpp` 文件（高密度对齐注释）。
    - 若为新类，同步生成 `.cpp` 骨架文件（所有函数体为空）。
- **工具**: `WriteCode::Declare`

### B. 实现阶段 (Define Action)
- **目的**: 针对具体函数编写实现细节。
- **操作**: `SetTarget` 锁定类后，使用 `Define` 命令覆盖特定函数体。
- **效果**: 精准查找 `.cpp` 中的函数位置，替换其内部逻辑，不干扰其他代码。
- **工具**: `WriteCode::Define`

---

## 2. 操作范式示例

### 第一步：战术声明 (API 设计)
```json
// 调用 Declare(name="AGeminiActor", path="...", content="{...}")
{
    "type": "class",
    "name": "AGeminiActor",
    "base": "AActor",
    "brief": "Gemini 代理 Actor",
    "children": [
        {
            "type": "method",
            "name": "MoveToTarget",
            "brief": "移动至目标",
            "params": [{"name": "Location", "type": "FVector"}]
        }
    ]
}
```

### 第二步：战术实现 (逻辑填补)
```javascript
// 先 SetTarget("AGeminiActor")
// 调用 Define(name="MoveToTarget", content="SetActorLocation(Location);")
```

---

## 3. 战术规则
1. **声明先行**: 严禁在未 `Declare` API 的情况下直接 `Define` 逻辑。
2. **增量声明**: 维护阶段涉及 API 变动时，必须先 `Declare` 更新 HPP，再 `Define` 实现。
3. **安全删除**: 使用 `Delete` 接口剥离不再需要的 API，系统会自动处理 HPP 与 CPP 的同步。

## 3. 输出期望
执行后，`WriteCode` 编译器将自动：
- 生成符合 `DataProcessor.hpp` 风格的 **Col 40 对齐注释**。
- 自动渲染 `UCLASS`, `USTRUCT`, `GENERATED_BODY` 等 UE5 专用宏。
- 维护层级缩进和 /// @brief 单行说明。

## 4. 实战演示
参考 [Gemini_ComplexDemo.py](file:///d:/InertialSensingAndAdvancedNavigationLab/CodeStyle/Gemini_ComplexDemo.py) 了解如何编写自动化测试脚本驱动此流程。
