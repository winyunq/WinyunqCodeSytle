---
name: RosCppNavigation
description: "ROS 与 C++ 导航逻辑规范，处理 C++ 命名规范、ROS 节点交互及预积分库调用。"
---

# RosCppNavigation Skill

## C++ 开发规范
- **命名规范**：遵循 UE5 风格的大驼峰命名法（PascalCase）。
- **类名前缀**：
    - `A`: 继承自 Actor 的类。
    - `U`: 继承自 Object 的类。
    - `F`: 纯 C++ 结构体或类。
- **内存管理**：在 UE5 环境下优先使用智能指针或 `UPROPERTY` 垃圾回收。

## ROS 交互
- **构建系统**：使用 `colcon` 或 `catkin`，确保 `CMakeLists.txt` 结构清晰。
- **消息定义**：自定义消息务必放在专用的 `msg` 文件夹下。
- **时间同步**：处理 IMU 数据时，注意 ROS 时间戳与传感器硬件时间戳的对齐。

## 惯性导航算法
- **预积分**：优先调用 `pypose` 提供的 C++ 接口或成熟的导航库。
- **坐标系转换**：处理 ENU 与 NED 转换时，务必在注释中明确轴向。
