class LockedDataProcessor:
    """
    @brief      演示用数据处理类
    @details    这是一个已经处于 Phase 2 (API Lock) 的类。
                Docstring 中没有 Gemini 字样，因此签名被锁定。
    """
    
    def __init__(self, initial_value):
        """
        @brief  初始化函数
        Args:
            initial_value (int): 初始值
        """
        # Phase 3 (Impl Lock): 初始化内部状态
        self.value = initial_value
        
    def complex_operation(self, factor):
        """
        @brief  执行复杂运算
        Returns:
            int: 运算结果
        """
        # 步骤 1: 检查输入有效性 (LOCKED)
        if factor < 0:
            return 0
            
        # 步骤 2: 执行核心乘法 (LOCKED)
        result = self.value * factor
        
        return result
