#include "Class.hpp"
#include <numeric>
#include <cmath>

namespace WinyunqSamples
{
    /// @brief 构造函数实现
    DataAnalyzer::DataAnalyzer() : cacheSize(1024)
    {
        /// 初始化内部状态
    }

    /// @brief analyze 函数实现
    double DataAnalyzer::analyze(const std::vector<double>& rawData)
    {
        /// 步骤 1: 基础有效性检查
        if (rawData.empty())
        {
            /// 如果数据为空，直接返回 0.0
            return 0.0;
        }

        /// 步骤 2: 计算平均值
        double sum = std::accumulate(rawData.begin(), rawData.end(), 0.0);
        double mean = sum / rawData.size();

        /// 步骤 3: 计算标准差
        double sq_sum = std::inner_product(rawData.begin(), rawData.end(), rawData.begin(), 0.0);
        double stdev = std::sqrt(sq_sum / rawData.size() - mean * mean);

        /// 步骤 4: 根据标准差评估置信度 (模拟逻辑)
        if (stdev < 0.1)
        {
            /// 数据非常集中，置信度高
            return 0.95;
        }
        else
        {
            /// 数据分散，置信度随方差降低
            return 1.0 / (1.0 + stdev);
        }
    }
}
