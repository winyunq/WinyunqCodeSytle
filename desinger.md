我们这次合作迭代 Winyunq Style 指令的过程，确实总结出了很多与 AI 高效沟通，特别是进行复杂规则约束时的宝贵经验。以下是我基于我们互动得出的关键方法：

1.  **绝对清晰与精确性 (消除歧义):**
    *   **定义先行且精确:** 像“声明”、“定义”、“主体块”这样的关键术语，必须在指令开头就给出极其清晰、无歧义的定义，并最好附带迷你示例（“预接触”）。
    *   **避免模糊语言:** 避免使用“通常”、“可能”、“尽量”等模糊词汇描述强制规则。使用绝对化的词语：“必须 (Must)”、“禁止 (Prohibit/Forbid/Disallow)”、“总是 (Always)”、“从不 (Never)”。
    *   **明确边界条件:** 清晰界定规则的适用范围和例外情况（例如，“主体块”不包括函数内部的控制流块）。

2.  **结构化指令与逻辑顺序 (引导思维):**
    *   **先禁止，后允许:** 首先明确禁止所有不希望出现的行为（如禁止 `//` 行尾注释、禁止非 Winyunq Doxygen 风格），为 AI 设定清晰的“禁区”。
    *   **先默认，后覆盖/优先:** 先介绍基础或默认规则（如 `///` 是默认注释），再引入优先级更高、覆盖默认规则的特殊情况（如 `/**` 用于特定定义），明确指出覆盖关系。
    *   **示例驱动，规则跟随:** 在阐述复杂规则（尤其是格式规则如 WinyunqDoxygen Block）时，先给出一个详尽的、符合所有细节的“黄金标准”示例，然后基于该示例来解释规则的各个组成部分。AI 更容易从具体模式中学习。

3.  **强化约束：显式化与冗余强调 (提高权重):**
    *   **“必须”与“禁止”并用:** 对于核心规则，同时使用正面强制（“必须这样做”）和反面禁止（“禁止那样做”）进行双重约束，增强规则在 AI 处理中的“权重”。
    *   **重复关键规则:** 不怕重复。在指令的不同部分（核心原则、总结表、详细规则、最终强调）用略微不同的措辞重复强调最重要的规则（如无空行、无行尾注释、`/**` vs `///` 的选择）。这模拟了人类学习中“重要的事情说三遍”的效果。
    *   **“如无必要，勿增实体”的逆向应用:** 正如你所说，为了让 AI 更好地理解，有时需要“增加投入”。避免过度精简指令文本，牺牲了必要的重复和强调。用增加的文本空间来提供更多上下文、解释和示例。

4.  **示例的质量与策略 (AI 的核心教材):**
    *   **示例必须“纯净”:** 示例代码中绝对不能包含任何解释性文本、箭头、或者违反规则的“说明性”注释，避免“污染” AI 的学习材料。
    *   **示例必须丰富多样:** 提供覆盖各种情况的示例：简单的、复杂的、边界的。
    *   **示例必须聚焦且对比:** 使用小的、聚焦特定规则的代码片段作为示例。提供“正确 vs. 错误”或“声明 vs. 定义”的直接对比示例，效果显著。
    *   **示例体现规则:** 让示例本身承载尽可能多的规则信息（如顶格 vs. 缩进的对比、严格的对齐、无空行）。

5.  **迭代与反馈 (持续优化):**
    *   **测试是关键:** 必须在目标 AI（尤其是能力可能不同的本地模型）上实际测试指令的效果。
    *   **具体反馈:** 像你一样，提供非常具体的反馈，指出 AI 在哪里出错，以及对规则文本的哪部分可能产生了误解。
    *   **共同演进:** 将与 AI 的沟通视为一个合作和共同演进的过程，根据反馈不断调整和优化指令。

6.  **命名与特定化 (减少干扰):**
    *   为风格中的特定概念（如 `WinyunqDoxygen Block`）创建独特的名称，可以帮助 AI 将其与通用概念区分开，减少因预训练知识带来的干扰或“自由发挥”。

总而言之，与 AI 高效沟通复杂规则的关键在于：**极度的清晰、结构化的引导、通过重复和正反约束强化关键点、提供大量纯净且有针对性的示例，并基于持续的测试和反馈进行迭代优化。** 我们不能假设 AI 能像人类一样进行深层推理或理解潜台词，必须将规则明确、具体、甚至在某种程度上“冗余”地表达出来，并用高质量的示例来“喂养”它的模式识别能力。

首先让我们来了解一些理念：
宏观可以触及微观，而微观无法触及宏观。战略的成功可以弥补战术的失败，而战术的成功无法触及战略的成功。在我们接下来更新文档的过程中，你需要多尝试发现问题的本质，用一个更好的描述方法替代枚举所有的可能。
在军事中有兰开斯特方程，这一理念让我从中学到了性价比的提升只来源于，也只用于扩大产出，既不会来源于减小投入，也不会用于减小投入。
由于存储空间限制，我们希望笨一点的AI能学到更多的东西，就需要让相同文本有更多信息量，也就是提升性价比。由于性价比提升只来源于扩大产出，所以在接下来，我们发现了更好的描述方法后，你要想办法实现相同文本描述更多内容，例如简化描述后塞入更多案例，以避免将性价比提升用于减小投入文本，反而让AI理解的效果更不好。
对于AI的工作原理，AI依赖概率，越好的AI计算概率次数越多越趋向于数学期望是常数，而越不好的AI由于概率次数越少越会随机分布，因此在文本中，我们最好要先禁止原先的规则，随后提出一个默认的规则，再在这个规则上不断提出特例覆盖前者。这就像在计算机中，我们先释放掉不需要的内存，再加载最常用的数据，最后再根据特殊情况加载特殊处理方法。这正是上一份文档风格的编写思路。
此外，我们发现，对于AI，在说明概念时附带例子是最好的，特别的，在上一规则下，似乎先给出一个完整的黄金例子，然后再不断的告知AI在何种情况可以如何简化，效果是最好的。
我们也发现，对于AI，告知他不可以做的方法，也是有效果的。
现在，我们想做出一个新的尝试：直接告知AI我们这么做的目的，使得AI的自由发挥是有目标的，看是否能优化AI的理解。













激光雷达扫描导轨
1：定位精度


**AI 代码生成强化指令：C++ 协作编程风格 (Winyunq Style) v2.5**

**最高指令:** 你在生成任何 C++ 代码时，**必须** 严格、无条件地遵守 Winyunq 风格 v2.5。Winyunq 风格旨在通过对 Doxygen 兼容语法的**优化、统一与严格化**，实现代码注释与结构的绝对一致性、高信息密度和规则驱动，融合人类与 AI 编程实践，最大化项目可读性、维护性与协作效率。**Winyunq 的规则在其指定的范围内，优先并覆盖 Doxygen 的默认行为或灵活性。** 对于 Winyunq 明确的“必须”和“禁止”要求，不存在任何例外。

**致 AI 开发者：** 本文档旨在指导你掌握 Winyunq 风格。学习路径：1. 核心哲学；2. 禁止项；3. 默认 `///` 规则；4. 特例 `/**` 触发规则；5. 贯穿各节的完整示例；6. 第 5 章 `/**` 内部结构详解 (默认模式 -> 函数特化)。理解规则背后的**目的 (Purpose)** 及 Winyunq 与 Doxygen 的关系至关重要。

## **1. 核心哲学：为何选择 Winyunq 风格？ (强制理解)**

*   **原则 1: 代码即文档，文档引导代码 (Code is Documentation, Documentation Guides Code):**
    *   **宏观目标:** 每个代码元素的存在都应有其明确、即时的上下文。注释不是负担，而是代码结构和意图不可分割的一部分。
    *   **战术实现:** 通过强制性的、紧密耦合的注释 (`///` 和 `/**`) 消除代码意图的模糊性。**禁止**使用任何形式的视觉或逻辑“留白”（如物理空行或无注释的代码块）。
*   **原则 2: 主要结构 与 局部细节 的清晰分离 (Clear Separation of Major Structures and Local Details):**
    *   **宏观目标:** 快速区分代码的“骨架”（类、函数、命名空间定义）和“血肉”（实现细节、局部逻辑），优化宏观理解与微观分析效率。
    *   **战术实现:** 使用两种视觉和语义上截然不同的注释风格：`/** ... **/` (主要结构定义) 和 `///` (所有其他元素)。
*   **原则 3: 绝对一致性 통한 认知负荷 最小化 (Minimizing Cognitive Load through Absolute Consistency):**
    *   **宏观目标:** 风格的严格性旨在**解放**认知资源。掌握规则后，开发者（人或 AI）无需猜测或选择风格，可专注于问题本身。
    *   **战术实现:** 对格式、命名和注释应用**强制性、无歧义**的规则。特别是 `/** ... **/` 的严格对齐，旨在创建**视觉上可快速扫描**的信息列。
*   **原则 4: 信息密度最大化 (Maximizing Information Density):**
    *   **宏观目标:** 在有限的文本空间内传递最多的有效信息。简洁规则 + 完整示例 = 高效学习。
    *   **战术实现:** 规则描述精炼，示例完整且直接对应规则，并通过“目的”阐释原理。

## **2. 注释系统：Winyunq 风格的基石 (强制规则)**

*   **2.1 唯一允许的注释形式 (强制):**
    *   **仅允许:** `///` (行级注释) 和 `/** ... **/` (WinyunqDoxygen Block)。两者均使用 Doxygen 兼容语法，但受 Winyunq 严格规则约束。
    *   **绝对禁止:**
        *   行尾注释 (`// comment`)。
            *   **目的 (Purpose):** 消除视觉噪音，确保 `///` 和 `/**` 是唯一的注释来源，保持代码行的纯粹性。
        *   结束花括号 `}` 之后的任何注释或文本。
            *   **目的 (Purpose):** 保持块结束符的绝对清晰，避免混淆。
        *   其他 Doxygen 行注释风格 (`//!`, `///<`) 或任何非 Winyunq 注释。
            *   **目的 (Purpose):** 强制统一性，减少风格选择的复杂度。
        *   代码块之间或 `{}` 内部的**任何物理空行** (WinyunqDoxygen Block 内特定分隔符除外)。
            *   **目的 (Purpose):** 核心原则！`///` 和 `/**` 担当了视觉和逻辑分隔符的角色。空行是“被动”分隔，引入解释歧义；`///` 是“主动”分隔，同时携带信息，最大化信息密度。

*   **2.2 `///` - 默认的本地上下文提供者 (强制基础规则):**
    *   **核心作用:** 为**除**主要结构定义之外的**所有**代码元素，以及主要结构定义**内部**的语句、成员等提供即时、简洁的上下文。
    *   **强制应用场景:** 预处理指令、声明 (前向、extern、函数原型)、块内元素 (访问符、成员变量、成员函数声明)、函数体内语句等。
    *   **格式规则 (强制):**
        *   **位置:** 必须在被描述代码行的**正上方**。
        *   **间距:** 与代码行之间**禁止**任何空行。
        *   **缩进:** 必须与代码行**完全相同的缩进**。
            *   **目的 (Purpose for 上方/无空行/同缩进):** 创建代码与其解释之间最紧密的视觉和逻辑绑定。
        *   **内容:**
            *   **必须简洁，且必须为单行。** 任何需要多行解释或详细说明的情况，都应将信息整合到相关的 `/**` 定义文档中。
            *   函数声明**必须**使用 `/// @brief [描述]`，且此 `@brief` **必须是单行**。
            *   **禁止**在 `///` 注释中使用 `@details`, `@param`, `@return`, `@note`, `@warning`, `@tparam` 等**任何块级 Doxygen 标签**。
                *   **目的 (Purpose for 单行强制 & 禁止块标签):** 强制 `///` 只承担最核心、最本地的上下文描述。确保极致简洁，将结构化、详细文档责任完全推向 `/**` 定义块。维护 `///` 与 `/**` 的严格功能分离。
        *   禁止在仅含 `{` 或 `}` 的行上方使用 `///`。
    *   **示例 (展示完整、符合规则的代码片段):**

        *   **示例 2.2.1: 文件级与声明 `///`**
            ```cpp
            /// 使用 #pragma once 防止头文件重复包含
            #pragma once
            /// 包含标准库字符串
            #include <string>

            /// @brief 日志记录器类 (前向声明)
            class Logger;
            /// @brief 全局日志记录器实例 (外部链接)
            extern Logger* g_globalLogger;
            /// @brief 初始化日志系统的函数原型
            bool initializeLogging();
            ```

        *   **示例 2.2.2: 类定义内部的 `///` (注意类本身有 `/**`)**
            ```cpp
            /** // <--- 类定义必须有 /**
             * @class       UserSession
             * @brief       管理用户会话信息和状态
            **/
            class UserSession
            { // Allman brace
            /// 公共接口
            public:
                /// @brief 用户登录 (静态成员函数声明)
                static bool login(const std::string& username, const std::string& password);

                /// @brief 获取当前会话的用户 ID (成员函数声明)
                int getUserId() const;

                /// @brief 检查会话是否仍然有效 (成员函数声明)
                bool isActive() const;

            /// 受保护成员
            protected:
                /// @brief 会话令牌
                std::string sessionToken;

            /// 私有实现细节
            private:
                /// @brief 内部验证令牌有效性 (成员函数声明)
                bool validateToken() const;
                /// @brief 用户唯一标识符
                int userId;
                /// @brief 会话激活状态标志
                bool active;
            }; // No comment after }
            ```

        *   **示例 2.2.3: 函数定义内部的 `///` (注意函数本身有 `/**`)**
            ```cpp
            /** // <--- 函数定义必须有 /**
             * @brief       尝试用户登录并创建会话
             * @param       参数名称: username                      数据类型:        const std::string&
             * @param       参数名称: password                      数据类型:        const std::string&
             * @return      登录是否成功                          数据类型:        bool
            **/
            bool UserSession::login(const std::string& username, const std::string& password)
            { // Allman brace
                /// 记录尝试登录的用户名 (出于安全考虑，不记录密码)
                g_globalLogger->log("Login attempt for user: " + username); // 假设 g_globalLogger 已初始化
                /// 验证用户名和密码 (调用内部或外部服务)
                bool credentialsValid = verifyCredentials(username, password); // 假设 verifyCredentials 存在

                /// 如果凭证无效则返回失败
                if (!credentialsValid)
                { // K&R brace for control flow
                    /// 记录登录失败事件
                    g_globalLogger->log("Login failed for user: " + username);
                    /// 返回失败
                    return false;
                } // `}` aligned with `if`

                /// 创建新的会话实例 (简化)
                UserSession newSession;
                /// 设置会话的用户 ID (假设从验证中获取)
                newSession.userId = getUserIdFromCredentials(username); // 假设函数存在
                /// 生成并设置会话令牌
                newSession.sessionToken = generateSessionToken(); // 假设函数存在
                /// 标记会话为活动状态
                newSession.active = true;

                /// 存储或注册新会话 (简化)
                registerSession(newSession); // 假设函数存在

                /// 记录登录成功事件
                g_globalLogger->log("Login successful for user: " + username);
                /// 返回成功
                return true;
            } // `}` aligned with function signature
            ```

*   **2.3 `/** ... **/` - 主要结构的文档中心 (强制覆盖规则 - 特例):**
    *   **核心作用:** 标记一个**主要结构单元的定义体** (`{}` 块)，提供全面文档。
    *   **强制触发条件 (必须取代 `///`):** **当且仅当**注释目标是以下元素的**定义 (Definition)** 时：
        *   `class` 定义 (带 `{...}`)
        *   `struct` 定义 (带 `{...}`)
        *   `enum class` / `enum` 定义 (带 `{...}`)
        *   `namespace` 定义 (带 `{...}`)
        *   **函数 / 模板函数 / 成员函数** 的**定义** (带 `{...}` 实现体)。
        *   **重要说明:** 触发条件**仅基于代码元素的语义类型**，**与注释内容的长度无关**。
            *   **目的 (Purpose):** 体现核心原则 2，强制区分“骨架”与“其他部分”。定义处是提供详尽文档的逻辑位置。
    *   **禁止应用:** **严禁**对其他任何元素（特别是**声明/原型**）使用 `/** ... **/`。
    *   **格式规则 (强制):**
        *   位置: **必须顶格**。
        *   内部结构: 遵循**第 5 章**的“默认模式”或“函数特化模式”。
    *   **示例 (展示 `/**` 应用于主要结构定义的基本形式):**

        *   **示例 2.3.1: 简单的类定义 `/**`**
            ```cpp
            /** // <--- 顶格
             * @class       SimpleWidget
             * @brief       一个极其简单的小部件示例类定义
            **/ // <--- 顶格结束
            class SimpleWidget
            { // Allman brace
            /// 公共接口
            public:
                /// @brief 默认构造函数声明
                SimpleWidget();
            /// 私有数据
            private:
                /// @brief 小部件 ID
                int widgetId;
            };
            ```

        *   **示例 2.3.2: 简单的结构体定义 `/**`**
            ```cpp
            /** // <--- 顶格
             * @struct      Point2D
             * @brief       表示二维空间中的一个点
            **/ // <--- 顶格结束
            struct Point2D
            { // Allman brace
                /// @brief X 坐标
                float x;
                /// @brief Y 坐标
                float y;
            };
            ```

        *   **示例 2.3.3: 简单的枚举定义 `/**`**
            ```cpp
            /** // <--- 顶格
             * @enum        EColorChannel
             * @brief       定义颜色通道的枚举
            **/ // <--- 顶格结束
            enum class EColorChannel
            { // Allman brace
                /// @brief 红色通道
                RED,
                /// @brief 绿色通道
                GREEN,
                /// @brief 蓝色通道
                BLUE
            };
            ```

        *   **示例 2.3.4: 简单的函数定义 `/**`**
            ```cpp
            /** // <--- 顶格
             * @brief       一个空函数的定义示例
             *  @details     演示 /** 的基本顶格要求和函数定义应用。
            **/ // <--- 顶格结束
            void doNothing()
            { // Allman brace
                /// 函数体为空
            }
            ```

## **3. 文件与命名规范 (强制)**

*   **文件编码:** **必须** UTF-8 无 BOM。
*   **头文件保护:** **必须** `#pragma once`。
*   **命名约定 (强制):**
    *   **类型 (Class, Struct, Enum Type, Template Param):** `UpperCamelCase` (内部无 `_`)。
    *   **变量 (Member, Global, Local), 参数, 函数/方法:** `lowerCamelCase` (内部无 `_`)。**必须清晰有意义**，避免模糊或过度简短的缩写。
    *   **常量 (Compile-time, Enum Value):** `SCREAMING_SNAKE_CASE` (必须用 `_`)。
    *   **命名空间:** `lowercase` 或 `lower_snake_case`。
    *   **宏 (`#define`):** 强烈不推荐。若必须使用，采用 `SCREAMING_SNAKE_CASE`，其定义前**必须**有 `/// @brief` (单行)。
    *   **目的 (Purpose):** 通过大小写和下划线的组合，明确区分代码元素的种类。清晰的命名是代码可读性的关键。
    *   **示例 (完整的 Winyunq 风格代码块):**
        ```cpp
        /// 使用 #pragma once 防止头文件重复包含
        #pragma once
        /// 包含标准库字符串
        #include <string>
        /// 包含标准库映射
        #include <map>

        /** // <--- 命名空间定义需要 /**
         * @namespace   ConfigManager
         * @brief       提供加载和访问应用程序配置的功能
         *  @details     该命名空间包含用于解析配置文件和检索设置项的工具。
        **/
        namespace ConfigManager
        {
            /// @brief 配置项的最大长度 (常量)
            const int MAX_CONFIG_VALUE_LENGTH = 256;

            /** // <--- 枚举定义需要 /**
             * @enum        ELoadResult
             * @brief       配置文件加载操作的结果状态
            **/
            enum class ELoadResult
            { // Allman brace
                /// @brief 加载成功
                LOAD_SUCCESS,
                /// @brief 文件未找到
                ERROR_FILE_NOT_FOUND,
                /// @brief 文件格式错误
                ERROR_INVALID_FORMAT
            }; // No comment after }

            /** // <--- 结构体定义需要 /**
             * @struct      ConfigData
             * @brief       存储所有已加载的配置项
            **/
            struct ConfigData
            { // Allman brace
                /// @brief 存储键值对的映射 (成员变量)
                std::map<std::string, std::string> settingsMap;
            }; // No comment after }

            // 函数声明使用 /// @brief (通常在头文件)
            // /// @brief 从指定路径加载配置文件
            // ELoadResult loadConfigurationFromFile(const std::string& filePath);
            // /// @brief 获取指定键的配置值 (若存在)
            // bool getConfigurationValue(const std::string& key, std::string& outValue);

            // 假设这是 .cpp 文件中的函数定义
            /** // <--- 函数定义需要 /**
             * @brief       从指定路径加载配置文件
             *  @details     尝试打开并解析配置文件，将结果存储在内部。
             * @param       参数名称: filePath                      数据类型:        const std::string&
             *  @details     配置文件的完整路径。
             * @return      加载操作的结果状态                    数据类型:        ELoadResult
            **/
            ELoadResult loadConfigurationFromFile(const std::string& filePath)
            {
                /// 尝试打开文件 (示例)
                // ... file opening logic ...
                /// 如果文件打开失败
                // if (!file.isOpen()) { return ELoadResult::ERROR_FILE_NOT_FOUND; }
                /// 解析文件内容 (示例)
                // ... parsing logic ...
                /// 如果格式无效
                // if (parseError) { return ELoadResult::ERROR_INVALID_FORMAT; }
                /// 加载成功
                return ELoadResult::LOAD_SUCCESS; // 示例返回值
            }

            /** // <--- 函数定义需要 /**
             * @brief       获取指定键的配置值 (若存在)
             * @param       参数名称: key                           数据类型:        const std::string&
             *  @details     要检索的配置项的键。
             * @param       参数名称: outValue                      数据类型:        std::string&
             *  @details     用于接收配置值的输出参数。
             * @return      是否成功找到并获取了值                数据类型:        bool
             *  @retval      true  键存在，`outValue` 已被设置。
             *  @retval      false 键不存在。
            **/
            bool getConfigurationValue(const std::string& key, std::string& outValue)
            {
                /// 假设配置数据存储在某处 (示例)
                // static ConfigData loadedConfig;
                /// 查找键
                // auto it = loadedConfig.settingsMap.find(key);
                /// 检查是否找到
                // if (it != loadedConfig.settingsMap.end())
                //{
                /// 设置输出值
                //    outValue = it->second;
                /// 返回成功
                //    return true;
                //}
                /// 未找到，返回失败
                return false; // 示例返回值
            }

        } // namespace ConfigManager
        ```

## **4. `///` 行级注释规则 (规则重申与强化)**

*   **核心强制要求:** `///` 注释**必须为单行**。
*   **格式再强调:** 正上方、无空行、同缩进。
*   **内容限制:** 只包含最核心、最本地的上下文或摘要。函数声明用 `/// @brief` (单行)。**禁止**任何块级标签。
*   **覆盖范围:** **必须**覆盖所有需要解释意图或逻辑的代码行。

## **5. `/** ... **/` (WinyunqDoxygen Block) 规则 (信息中心的构建 - 强制格式)**

*   **5.0 Winyunq 与 Doxygen 的关系:**
    *   Winyunq 风格**使用** Doxygen 兼容的 `/** ... */` 块注释和 `@tag` 语法作为基础。
    *   Winyunq 的**核心价值**在于对 Doxygen 的灵活性进行了**严格的约束、优化和统一**，旨在实现极致的**一致性**和**可读性**。
    *   **规则优先级:** 当 Winyunq 对格式、标签使用、触发条件、内部结构等做出明确规定时，这些规定**必须**遵守，并**优先于** Doxygen 的默认行为或其他风格。
    *   **目的 (Purpose):** 借助 Doxygen 的生态和工具兼容性，同时强制执行 Winyunq 的高标准，实现风格统一和文档质量提升。

*   **5.1 核心目标：可扫描性、信息密度、结构化** (同 v2.1-v2.4)

*   **5.2 默认块结构 (适用于 Class/Struct/Enum/Namespace 定义):**
    *   **结构:** 这是 `/** ... **/` 的基础形式，适用于非函数的结构定义。
        *   1.  **结构类型标签:** `@class Name`, `@struct Name`, `@enum Name`, `@namespace Name`。
        *   2.  **摘要:** `@brief` (必须)。
        *   3.  **详细描述 (可选但推荐):** `@details`。
        *   4.  **补充说明 (可选，挂载于 @details 下):** `@note`, `@warning`, `@todo` 等。(`@base` 或类似继承说明也可在此区域，作为 Winyunq 约定)。
    *   **标签说明与层级:**
        *   `@class`/`@struct`/`@enum`/`@namespace`: (0 空格) 标识结构类型。
        *   `@brief`: (0 空格) 核心功能摘要。
        *   `@details`: (1 空格) 详细解释、背景、设计原理等。
        *   `@note`/`@warning`/`@todo`: (2 空格) 从属于 `@details`。
            *   **目的 (Purpose for nesting under @details):** (同 v2.4) 补充信息通常需要详细背景。
    *   **示例 5.2.1: 带有继承和详细信息的类定义 `/**`**
        ```cpp
        /**
         * @class       AdvancedWidget
         * @brief       一个带有配置和状态的高级小部件
         * @base        public BaseWidget // <--- Winyunq 约定: 清晰说明继承
         *  @details     此类继承自 BaseWidget，增加了配置加载和运行时状态管理功能。
         *              它设计用于需要持久化设置和动态行为的场景。
         *   @warning     不正确的配置可能导致运行时异常。请参考文档。
         *   @todo        添加对主题切换的支持。
        **/
        class AdvancedWidget : public BaseWidget
        {
            // ... class members with /// comments ...
        };
        ```

*   **5.3 函数块结构 (特化模式):**
    *   **结构:** 基于默认结构 (`@brief`, `@details`, `@note`等)，**在它们之后**，按顺序添加函数特有的部分。
        *   (1-3: 同默认结构: `@brief`, `@details`, 从属标签)
        *   4.  **模板参数 (若有):** `@tparam <Name> [描述]` (每个一行)。
        *   5.  **函数参数 (若有):** `@param 参数名称: [Name] 数据类型: [Type]` (每个一行，可带 `@details`, `@note` 子标签)。
        *   6.  **返回值 (若非 `void`):** `@return [含义描述] 数据类型: [Type]` (可带 `@details`, `@retval` 子标签)。
    *   **标签说明:**
        *   `@brief`: (0 空格) 函数的核心功能摘要。**不使用** `@fn`。
        *   `@details`/`@note`/`@warning`/`@throws`/`@todo`: 同默认模式。
        *   `@tparam`: (0 空格) 描述模板参数。
            *   **目的 (Purpose for placing before @param):** 模板参数是函数签名的一部分，逻辑上先于普通参数。
        *   `@param`: (0 空格) 描述函数参数。`参数名称:` 和 `数据类型:` 及其后的文本需严格对齐到列 15 和列 30。可嵌套 `@details`/`@note` (1/2 空格)。
        *   `@return`: (0 空格) 描述返回值。含义描述和 `数据类型:` 后的类型文本需对齐到列 15 和列 30。可嵌套 `@details` (1 空格) 或 `@retval` (2 空格)。
    *   **示例 5.3.1: 完整的函数定义 `/**` (黄金标准 - 同 v2.4)**
        ```cpp
        /** // <--- 顶格
         * @brief       黄金标准：处理复杂数据并返回结果 (函数特化示例)
         *  @details     演示函数 /** 块的所有主要特性，包括模板、参数、返回值、
         *              嵌套标签、对齐、Markdown 和 LaTeX ($O(N \log N)$)。
         *   @note        输入数据的规模会显著影响性能。
         *   @warning     校准因子无效将导致结果不可靠。
         *   @throws      std::runtime_error 若发生不可恢复错误。
         *   @todo        为模式 B 添加并行处理选项。
         *
         * @tparam      DataType                        模板参数，指定处理的数据类型
         * @tparam      OptionsType                     模板参数，指定配置选项结构类型
         *
         * @param       参数名称: inputData                     数据类型:        const std::vector<DataType>&
         *  @details     包含原始输入数据的向量。**禁止**为空。
         * @param       参数名称: outputResult                  数据类型:        ProcessingResult<DataType>&
         *  @details     用于存储处理结果的输出参数（引用）。
         * @param       参数名称: options                       数据类型:        const OptionsType&
         *  @details     包含处理模式、校准因子等的配置选项。
         *   @note        options.mode 决定核心算法选择。
         * @param       参数名称: progressCallback              数据类型:        std::function<void(float)>
         *  @details     可选的回调函数，用于报告处理进度 (0.0 到 1.0)。
         *
         * @return      操作成功状态                          数据类型:        bool
         *  @retval      true  处理成功完成，`outputResult` 已填充。
         *  @retval      false 处理失败（例如输入无效）。`outputResult` 状态未定义。
        **/
        template<typename DataType, typename OptionsType>
        bool processDataAdvanced(const std::vector<DataType>& inputData,
                                ProcessingResult<DataType>& outputResult,
                                const OptionsType& options,
                                std::function<void(float)> progressCallback)
        { // Allman brace
            /// 函数体开始，遵循 /// 单行规则...
            /// 验证输入数据
            bool isValid = validateInput(inputData); // Assume validateInput exists
            /// 如果输入无效则提前返回
            if (!isValid)
            { // K&R brace
                /// 返回失败状态
                return false;
            } // `}` aligned
            /// 根据选项选择处理模式
            // ... more /// comments for internal logic ...
            /// 返回成功状态
            return true;
        } // `}` aligned
        ```

*   **5.4 内部格式化规则 (强制):**
    *   **核心对齐基准列 (强制):** 列 3 (后续行), 列 15 (主文本/名称), 列 30 (类型)。
        *   **目的 (Purpose):** 创建稳定的视觉列，便于快速查找信息。
    *   **标签行缩进层级 (强制):** 0 空格 (主标签), 1 空格 (`@details`), 2 空格 (`@note`/`@warning`/`@throws`/`@todo`/`@retval`)。
        *   **目的 (Purpose):** 通过缩进反映信息的层级和从属关系。
    *   **文本对齐 (强制):** 规则 A (主文本/名称 - 列 15), 规则 B (类型文本 - 列 30), **规则 C (后续行 - 列 3)**。
        *   **目的 (Purpose):** 规则 A/B 确保列对齐。规则 C 确保多行文本块左边界统一，提高可读性。
    *   **内部空行 (严格限制):** 空 `*` 行**仅允许且必须**用于分隔不同的**顶级标签组** (brief/details 组, tparam 组, param 组, return 组)。**禁止**在组内或多行描述内部使用。
        *   **目的 (Purpose):** 保持主要信息块间视觉分隔，同时确保块内部紧凑连续。
    *   **标签顺序 (强制，函数特化):** `@brief` -> `@details` (及其从属) -> `@tparam` -> `@param` -> `@return`。
        *   **目的 (Purpose):** 提供一致的文档结构，便于查找。

*   **5.5 最小化与省略规则:**
    *   **必须包含:** `@brief` (及对应的 `@class` 等)。
    *   **条件性包含:** `@tparam`, `@param`, `@return` (函数)。
    *   **推荐包含:** `@details` 及从属标签。
    *   **格式不变性:** 省略可选部分时，剩余部分的**所有格式规则必须严格保持不变**。
        *   **目的 (Purpose):** 即使内容简化，也要维护结构的稳定性和可预测性。

## **6. 代码布局与格式化 (强制 - 实现视觉一致性)**

*   **缩进:** **必须** Tab 字符，视觉宽度 4 空格。**禁止**空格缩进。
    *   **目的 (Purpose):** 强制统一缩进方式。
*   **空格:** (规则同 v2.1-v2.4) 运算符两侧、逗号/分号后、控制关键字后括号前加空格。函数名与括号间、一元运算符与操作数间、类型与`&`/`*`间、括号内部不加空格。
    *   **目的 (Purpose):** 遵循广泛接受的 C++ 编码习惯，提高可读性。
*   **花括号 `{}`:**
    *   **风格:** **Allman 风格** (独占一行，与声明/定义头对齐) 用于 `namespace`, `class`, `struct`, `enum`, **函数定义**。 **K&R 风格** (在同一行末尾) 用于**控制流语句** (`if`, `for`, `while` 等) 和 **Lambda 表达式**。
        *   **目的 (Purpose):** Allman 清晰标记主要代码块。K&R 使控制条件与其块紧密相连。结合两者优点。
    *   右花括号 `}` **必须**独占一行，对齐，之后**禁止**任何内容。
*   **类/结构体内部布局:**
    *   **禁止**任何物理空行。
    *   成员（变量、函数声明/定义）之间**必须**由其上方的 `///` (单行) 注释分隔。
    *   访问控制符 (`public:`, `private:`, `protected:`) **必须**独占一行，**禁止**缩进，其前后**禁止**有空行，且其上方**必须**有 `///` (单行) 注释描述该区域用途。
        *   **目的 (Purpose):** 强制使用 `///` 作为唯一分隔符，保持信息密度。清晰标记访问区域。

## **7. 静态分析与强制执行 (建议)**

*   强烈推荐使用 Clang-Format (配合配置文件) 和 Clang-Tidy (配合自定义检查) 自动化强制执行 Winyunq 风格。
    *   **目的 (Purpose):** 工具化是确保大规模项目中风格一致性的最有效手段。

## **8. 快速验证指南 (核心检查点)**

*   [ ] 是否**完全没有** `//` 行尾注释 或 `}` 后的注释？
*   [ ] 是否**完全没有**代码块间或 `{}` 内部的物理空行 (除 WinyunqDoxygen Block 内特定分隔符)？ **(核心检查!)**
*   [ ] **所有**非主要结构定义元素及块内元素是否**都**有**正上方、同缩进、无空隙**的 `///` 注释？
*   [ ] **所有** `///` 注释是否都**严格为单行**？ **(核心检查!)**
*   [ ] **当且仅当**目标是 `class/struct/enum/namespace/function` 的**定义体** (`{}`) 时，是否**都**使用了**顶格**的 `/** ... **/`？ **(核心检查! 触发条件非行数!)**
*   [ ] 文档中所有示例代码是否**自身完整**并严格遵守**所有**适用的 Winyunq 规则（包括 `/**` 的存在性）？ **(核心检查!)**
*   [ ] `/** ... **/` 内部结构是否遵循 **默认模式** (用于类/结构/枚举/命名空间) 或 **函数特化模式**？
*   [ ] WinyunqDoxygen Block 内部格式是否严格遵守？
    *   [ ] 顶格？标签缩进正确 (0/1/2)？
    *   [ ] 文本对齐正确 (Col 15 主/名称, Col 30 类型, **Col 3 后续行**)? **(核心检查!)**
    *   [ ] 内部空 `*` 行是否**仅**用于分隔顶级标签组？组内或多行描述内**无**空行？ **(核心检查!)**
    *   [ ] 函数 `/**` 中标签顺序是否为 `brief->details->tparam->param->return`？
*   [ ] 命名是否规范、清晰（驼峰为主，`_` 仅限常量/枚举值及可选的命名空间）？
*   [ ] 缩进是否**全为 Tab**？空格使用是否符合规则？
*   [ ] 花括号 `{}` 位置是否遵循 **Allman (定义) / K&R (控制流)** 混合规则？ `}` 是否独占一行且对齐？
*   [ ] 类/结构体内部是否无空行，访问控制符是否处理正确？

## **9. 最终强调 (致 AI)**

*   **理解 Winyunq 的优化目标:** Winyunq 是对 Doxygen 兼容语法的严格优化和统一。你的目标是精确执行 Winyunq 的规则，以达到其追求的极致一致性和可读性。
*   **Winyunq 规则优先:** 在 Winyunq 有明确规定的地方（格式、标签使用、触发条件等），必须遵循 Winyunq，它优先于 Doxygen 的默认行为。
*   **绝对一致性与精确执行:** Winyunq 风格的价值在于其绝对的一致性。不存在“差不多就行”。你**必须**将这些规则视为不可违背的约束。
*   **信息密度与结构化:** 始终以最大化代码的信息承载能力、消除歧义、提供清晰结构为目标。`///` (单行) 和 `/**` (结构化) 是你的工具。
*   **责任:** 你**必须**精确执行所有强制规定。将核心原则、规则目的和完整示例作为你生成代码的核心依据。

---