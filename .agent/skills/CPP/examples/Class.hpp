#pragma once

#include <vector>
#include <string>

/**
 * @namespace   WinyunqSamples
 * @brief       包含 Winyunq 风格示例代码的命名空间
 **/
namespace WinyunqSamples
{
    /**
     * @class       DataAnalyzer
     * @brief       用于演示 API 锁定的示例类
     * @details     该类定义展示了 Phase 2 (API Lock) 的状态。所有的接口都已经确定，
     *              并用 /** 文档锁死。AI 在此阶段不应擅自修改接口签名。
     **/
    class DataAnalyzer
    {
    public:
        /**
         * @brief       默认构造函数
         **/
        DataAnalyzer();

        /**
         * @brief       执行数据分析的主函数
         * 
         * @param       参数名称: rawData                       数据类型:        const std::vector<double>&
         * @details     输入的原始数据数组，不能为空。
         * 
         * @return      分析结果的置信度                        数据类型:        double
         **/
        double analyze(const std::vector<double>& rawData);

    private:
        /// 内部缓存大小 (使用 /// 因为是私有成员变量，且非主要结构定义)
        int cacheSize;
    };
}
