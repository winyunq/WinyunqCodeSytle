import re
import json

class WinyunqParser:
    """
    Winyunq 战术解析器 (Taxonomy Parser)
    利用正则表达式提取 C++/UE5 代码结构、接口签名及 Doxygen 注释。
    """

    def __init__(self):
        # 匹配类/结构体 (UE5 宏设为可选)
        self.re_class = re.compile(r"(?P<comment>(?:/\*\*[\s\S]*?\*/|///.*?\n\s*)*)\s*(?:UCLASS\(.*?\)\s*)?"
                                   r"(?:class|struct)\s+(?P<prefix>\w+_)?(?P<name>\w+)\s*(?::\s*(?:public|protected|private)\s+[\w\d_:]+)?\s*\{", re.MULTILINE)

        # 匹配方法 (支持 UE5 宏可选，支持声明 ';' 或定义 '{')
        self.re_method = re.compile(r"(?P<comment>(?:/\*\*[\s\S]*?\*/|///.*?\n\s*)*)\s*(?:UFUNCTION\(.*?\)\s*)?"
                                    r"(?P<mods>(?:virtual|static|inline)\s+)*(?P<return>[\w\d_:<>*&]+\s+)?\b(?P<name>\w+)\b\s*\((?P<params>.*?)\)"
                                    r"\s*(?P<specs>(?:const|override|final|PURE_VIRTUAL\(.*?\)|=[^;{]+)\s*)*(?:;|(?=\{))", re.MULTILINE | re.IGNORECASE)

        # 匹配属性 (UE5 宏可选)
        self.re_property = re.compile(r"(?P<comment>(?:/\*\*[\s\S]*?\*/|///.*?\n\s*)*)\s*(?:UPROPERTY\(.*?\)\s*)?"
                                      r"(?P<mods>(?:static|inline|mutable)\s+)*(?P<type>[\w\d_:<>*&]+\s+)\b(?P<name>\w+)\b\s*(?:=[^;]+)?\s*;", re.MULTILINE | re.IGNORECASE)

    def parse_doxygen(self, comment_text):
        """将 Doxygen 块解析为 Winyunq 风格的 JSON"""
        if not comment_text: return {}

        # 清理行首的 * 或 ///
        lines = []
        for line in comment_text.split("\n"):
            line = line.strip()
            if line.startswith("/**") or line.endswith("*/"): continue
            line = re.sub(r"^\s*\*\s*", "", line)
            line = re.sub(r"^\s*///\s*", "", line)
            if line: lines.append(line)

        content = " ".join(lines)
        result = {"brief": "", "details": "", "params": [], "return": ""}

        # 提取 @brief / @details 等
        brief_match = re.search(r"[@\\]brief\s+(.*?)(?=@|\\|$)", content)
        if brief_match: result["brief"] = brief_match.group(1).strip()

        details_match = re.search(r"[@\\]details\s+(.*?)(?=@|\\|$)", content)
        if details_match: result["details"] = details_match.group(1).strip()

        # 提取参数
        for p_match in re.finditer(r"[@\\]param\s+(\w+)\s+(.*?)(?=@|\\|$)", content):
            result["params"].append({"name": p_match.group(1), "brief": p_match.group(2).strip()})

        return result

    def get_taxonomy(self, code):
        """提取代码中的所有顶级对象及其第一层成员"""
        taxonomy = []

        # 1. 查找所有类
        class_pos = []
        for match in self.re_class.finditer(code):
            class_name = match.group("name")
            comment = self.parse_doxygen(match.group("comment"))

            # 简单查找类结束位置（寻找匹配的 }）
            start = match.end()
            bracket_count = 1
            end = start
            for i in range(start, len(code)):
                if code[i] == '{': bracket_count += 1
                elif code[i] == '}': bracket_count -= 1
                if bracket_count == 0:
                    end = i
                    break

            class_pos.append((match.start(), end, class_name))
            class_code = code[start:end]

            # 提取类内成员
            members = []
            for m_match in self.re_method.finditer(class_code):
                members.append({
                    "type": "method",
                    "name": m_match.group("name"),
                    "full_name": f"{class_name}::{m_match.group('name')}",
                    "return": (m_match.group("return") or "void").strip(),
                    "params": m_match.group("params").strip(),
                    "doc": self.parse_doxygen(m_match.group("comment"))
                })

            for p_match in self.re_property.finditer(class_code):
                members.append({
                    "type": "variable",
                    "name": p_match.group("name"),
                    "full_name": f"{class_name}::{p_match.group('name')}",
                    "data_type": p_match.group("type").strip(),
                    "doc": self.parse_doxygen(p_match.group("comment"))
                })

            taxonomy.append({
                "type": "class",
                "name": class_name,
                "doc": comment,
                "children": members
            })

        # 2. 查找孤立对象 (不在类中的函数/变量 - 简化处理)
        # 暂不实现复杂的全局搜索，优先满足 UE5 类结构需求
        return taxonomy

if __name__ == "__main__":
    # 简单自测
    test_code = """
    /**
     * @brief 测试类
     */
    UCLASS()
    class ATestActor : public AActor {
        GENERATED_BODY()
    public:
        /**
         * @brief 开始游戏
         * @param DeltaTime 时间增量
         */
        virtual void BeginPlay(float DeltaTime) override;

        /// @brief 生命值
        UPROPERTY()
        float Health = 100.0f;
    };
    """
    parser = WinyunqParser()
    tax = parser.get_taxonomy(test_code)
    print(json.dumps(tax, indent=2, ensure_ascii=False))
