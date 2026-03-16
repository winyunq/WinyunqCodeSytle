import os
import sys
import re
import json

try:
    from WinyunqReadBase import WinyunqReadBase, WinyunqAction
except ImportError:
    # 适配 sub-skill 运行时的导入路径
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "WinyunqCore", "scripts")))
    from WinyunqReadBase import WinyunqReadBase, WinyunqAction

class ReadCode(WinyunqReadBase):
    """
    CPP 专属侦察工具 [TACTICAL OVERWRITE]
    支持穿透式作用域解析 (Scope Penetration) 与 Winyunq 风格读取。
    """

    def resolve_scoped_content(self, content, name):
        """
        深度解析 C++ 作用域块。支持 A::B::C。
        如果解析失败，尝试直接在内容中定位 leaf_name。
        """
        if not name: return content
        parts = name.split("::")
        
        current_scope = content
        last_found_scope = content
        
        for part in parts:
            # 匹配 类/命名空间/函数 开始的地方
            # 兼容：void addRecords(...), class DataProcessor, namespace CollaborativeAi
            pattern = fr"\b(class|struct|namespace|void|double|int|size_t|auto|enum\s+class)?\s*{re.escape(part)}\b[\s\S]*?\{{"
            match = re.search(pattern, current_scope)
            
            if match:
                # 括号平衡提取
                start_ptr = match.end() - 1
                count = 0
                for i in range(start_ptr, len(current_scope)):
                    if current_scope[i] == '{': count += 1
                    elif current_scope[i] == '}':
                        count -= 1
                        if count == 0:
                            current_scope = current_scope[start_ptr : i+1]
                            last_found_scope = current_scope
                            break
                else: 
                    # 括号不匹配
                    return last_found_scope
            else:
                # 如果中间某个环节断了，尝试在全局全文搜最后一个 part (针对跨层直接搜成员的情况)
                final_part = parts[-1]
                match_leaf = re.search(fr"\b{re.escape(final_part)}\b", content)
                if match_leaf:
                    # 返回包含该行的一个上下文块 (暂定)
                    start = max(0, match_leaf.start() - 100)
                    end = min(len(content), match_leaf.end() + 100)
                    return content[start:end]
                return last_found_scope
                
        return current_scope

    @WinyunqAction("List", "C++ 穿透式扫描：列出当前作用域下的成员", 
                   params=[{"name": "name", "required": False, "doc": "对象名 (支持 A::B)"}])
    def list_objects(self, name=None):
        file_path = self.resolve_file_by_name(name)
        if not file_path: return "[]"
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        scoped = self.resolve_scoped_content(content, name)
        # 简单提取成员: 查找变量定义或函数声明
        members = re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s*[;=({]", scoped)
        # 过滤掉 C++ 关键字
        keywords = {'if', 'else', 'for', 'while', 'return', 'switch', 'case', 'break', 'try', 'catch', 'throw'}
        result = sorted(list(set([m for m in members if m not in keywords])))
        return json.dumps(result, ensure_ascii=False)

    @WinyunqAction("Declaration", "读取 C++ 声明（不含实现体）", 
                   params=[{"name": "name", "required": True}])
    def read_declaration(self, name):
        # 逻辑：寻找声明并移除花括号内的内容
        return self.execute_declaration(name)

    @WinyunqAction("Definition", "读取 C++ 完整定义（穿透定位）", 
                   params=[{"name": "name", "required": True}])
    def read_definition(self, name):
        return self.read_for_edit(name)

    @WinyunqAction("ReadForEdit", "C++ 维护性读取：完整读入代码及注释", 
                   params=[{"name": "name", "required": True}])
    def read_for_edit(self, name):
        file_path = self.resolve_file_by_name(name)
        if not file_path: return f"Error: {name} not found."
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        return self.resolve_scoped_content(content, name)

    @WinyunqAction("Reference", "检索 C++ 引用位置", 
                   params=[{"name": "name", "required": True}])
    def read_reference(self, name):
        return self.execute_reference(name)

if __name__ == "__main__":
    tool = ReadCode()
    if "--manifest" in sys.argv:
        print(json.dumps(tool.get_manifest(), ensure_ascii=False))
