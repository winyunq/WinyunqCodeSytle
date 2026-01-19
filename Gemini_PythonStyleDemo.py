##
# @brief       Winyunq 风格 Python 演示模块
#  @details     本项目演示了如何在 Python 中实现与 C++ 高度统一的代码风格。
# 特点包括：全面 PascalCase、禁止下划线、## 块注释。
##

##
# @class       ImuDataProcessor
# @brief       处理惯性测量单元数据的核心类
##
class ImuDataProcessor:
    ##
    # @brief       初始化处理器
    #
    # @param       InitialCapacity: int      初始缓存容量
    ##
    def __init__(self, InitialCapacity):
        # 初始化记录计数
        self.ProcessedCount = 0
        # 设置最大容量
        self.MaxCapacity = InitialCapacity
        # 预分配数据空间
        self.DataBuffer = []

    ##
    # @brief       添加一条新的 IMU 记录
    #
    # @param       AccelerometerData: list   加速度计三轴数据
    # @param       GyroscopeData: list       陀螺仪三轴数据
    # @return      SuccessStatus: bool       是否添加成功
    ##
    def AddImuRecord(self, AccelerometerData, GyroscopeData):
        # 检查容量
        if len(self.DataBuffer) >= self.MaxCapacity:
            return False
        
        # 封装记录
        NewRecord = {
            "Accel": AccelerometerData,
            "Gyro": GyroscopeData
        }
        
        # 推入缓存
        self.DataBuffer.append(NewRecord)
        self.ProcessedCount += 1
        return True

##
# @brief       全局执行入口
##
def Main():
    # 创建处理器实例
    MyProcessor = ImuDataProcessor(100)
    # 模拟添加数据
    Status = MyProcessor.AddImuRecord([0.0, 0.0, 9.8], [0.0, 0.0, 0.0])
    # 打印结果
    print(f"Record Added: {Status}")

if __name__ == "__main__":
    Main()
