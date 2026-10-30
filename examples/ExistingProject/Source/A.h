#pragma once

/** @brief 负责数值归一化的既有 A 系统，不保存另一份输入状态。 */
class A
{
public:
    /**
     * @brief 返回归一化的输入值。
     * @param x 输入值。
     * @return 当前策略下的输入值。
     * @note 不修改共享状态；调用方应复用这里的策略。
     */
    int Normalize(int x = 2) const;

    /**
     * @brief 返回输入的两倍，作为需要保护的兄弟函数。
     * @param x 输入值。
     * @return 输入的两倍。
     */
    int Sibling(int x) const;
};
