import os
import sys
import json
try:
    from WinyunqBase import WinyunqBase, WinyunqAction
except ImportError:
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from WinyunqBase import WinyunqBase, WinyunqAction

class WriteCode(WinyunqBase):
    """
    战斗支柱 (Write Pillar)
    战术写入：在战略 Working Path 内通过名称定位并生成 Gemini 草稿。
    """
    
    @WinyunqAction("Declare", "声明 API 结构 (HPP) 并同步生成/补充空实现骨架 (CPP)", 
                   params=[{"name": "name", "required": True, "doc": "类名或文件名"}, 
                           {"name": "content", "required": True, "doc": "代码或 JSON 协议"},
                           {"name": "path", "required": False, "doc": "指定 HPP 路径"}])
    def declare(self, name, content, path=None):
        target_name = self.state.get("target_name")
        raw_json_data = None
        
        # 1. JSON 预编译与数据提取
        try:
            if content.strip().startswith("{") and content.strip().endswith("}"):
                raw_json_data = json.loads(content)
                if isinstance(raw_json_data, dict) and "type" in raw_json_data:
                    content = self._compile_json_to_winyunq_comment(raw_json_data)
        except: pass

        # 2. HPP 处理 (全局创建 vs 靶向增量)
        # 行为策略：如果是顶层类声明 (type: class)，强制执行全局创建/查找流；
        # 否则 (方法/属性等)，若有 Target 则执行增量式注入。
        is_top_level_class = raw_json_data and raw_json_data.get("type", "").lower() == "class"
        
        if not is_top_level_class and not path and target_name and name != target_name:
            result = self._incremental_declare(name, content, target_name)
            # 增量场景：如果声明的是 method，也要同步 CPP (到当前的 Target)
            if "Success" in result and raw_json_data and raw_json_data.get("type") == "method":
                self._ensure_cpp_skeleton({"type": "class", "name": target_name, "children": [raw_json_data]}, target_name)
        else:
            result = self._global_declare(name, content, path)
            # 全局场景：如果是类 JSON，同步 CPP (到自身)
            if "Success" in result and raw_json_data and raw_json_data.get("type") == "class":
                self._ensure_cpp_skeleton(raw_json_data, name)

        return result

    def _ensure_cpp_skeleton(self, data, name):
        """为类中的所有方法在 .cpp 中生成/补充空实现"""
        if data.get("type", "").lower() != "class": return
        
        class_name = data["name"]
        cpp_path = self.resolve_file_by_name(class_name, preferred_ext=".cpp")
        
        if not cpp_path:
            # 策略：CPP 应该与 HPP 在同一个目录下
            hpp_path = self.resolve_file_by_name(class_name, preferred_ext=".hpp")
            if hpp_path:
                cpp_path = os.path.splitext(hpp_path)[0].replace(self.settings.get("gemini_prefix", ""), "") + ".cpp"
            else:
                work_path = self.state.get("work_path", self.root)
                cpp_path = os.path.join(work_path, f"{class_name}.cpp")
        
        write_path = self.get_write_path(cpp_path)
        content = ""
        if os.path.exists(write_path):
            with open(write_path, 'r', encoding='utf-8') as f: content = f.read()
        elif os.path.exists(cpp_path):
            with open(cpp_path, 'r', encoding='utf-8') as f: content = f.read()

        if not content:
            content = f'#include "{class_name}.hpp"\n\n'

        # 提取所有方法
        for child in data.get("children", []):
            if child.get("type", "").lower() == "method":
                m_name = child["name"]
                m_return = child.get("return_type", "void")
                params = ", ".join([f"{p['type']} {p['name']}" for p in child.get("params", [])])
                stub = f"\n{m_return} {class_name}::{m_name}({params}) {{\n    \n}}\n"
                if f"{class_name}::{m_name}" not in content:
                    content += stub

        os.makedirs(os.path.dirname(write_path), exist_ok=True)
        with open(write_path, 'w', encoding='utf-8') as f:
            f.write(content)

    def _global_declare(self, name, content, path):
        existing_file = self.resolve_file_by_name(name, preferred_ext=".hpp")
        target_path = path

        if not target_path:
            work_path = self.state.get("work_path", self.root)
            ext = ".hpp" if self.settings.get("winyunqcodestyle") == "CPP" else ".py"
            target_path = os.path.join(work_path, f"{name}{ext}")
        else:
            target_path = os.path.normpath(os.path.abspath(target_path))

        # 冲突检测：同名但路径不同
        if existing_file:
            existing_abs = os.path.normpath(os.path.abspath(existing_file))
            expected_shadow = os.path.normpath(self.get_write_path(target_path))
            if os.path.normcase(existing_abs) != os.path.normcase(target_path) and \
               os.path.normcase(existing_abs) != os.path.normcase(expected_shadow):
                return f"Strategic Conflict: API '{name}' already exists at path: {existing_file}"

        write_path = self.get_write_path(target_path)
        os.makedirs(os.path.dirname(write_path), exist_ok=True)
        with open(write_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"Mission Tactical Success: Declared '{name}' at {write_path}"

    def _incremental_declare(self, name, content, target_name):
        target_file = self.resolve_file_by_name(target_name, preferred_ext=".hpp")
        if not target_file:
            return f"Error: Target API '{target_name}' not resolved."
            
        write_path = self.get_write_path(target_file)
        if not os.path.exists(write_path):
            with open(target_file, 'r', encoding='utf-8') as f:
                file_content = f.read()
        else:
            with open(write_path, 'r', encoding='utf-8') as f:
                file_content = f.read()

        if content.strip() in file_content:
            return f"No Change: API '{name}' identical to existing content in '{target_name}'."

        import re
        pattern = rf"(\s*(?:/\*\*(?:(?!\*/).)*\*/|///.*?\n)\s*)?(\s*(?:UPROPERTY|UFUNCTION)\(.*?\)[\s\n]*)?([ \t]*[\w\d_:<>*&]+\s+\b{name}\b[\s\n]*(?:\(.*?\))?;)"
        if re.search(pattern, file_content, re.DOTALL):
            new_file_content = re.sub(pattern, content, file_content, count=1, flags=re.DOTALL)
            with open(write_path, 'w', encoding='utf-8') as f:
                f.write(new_file_content)
            return f"Mission Tactical Success: Redeclared '{name}' in target '{target_name}'."

        if "};" in file_content:
            style = self.doxygen_style
            if not style.get("block_comment_indent", False):
                def si(l):
                    s = l.strip()
                    return not (s.startswith("/**") or s.startswith("*") or s.startswith("**/"))
                indented = "\n".join(["    " + l if si(l) and l.strip() else l for l in content.split("\n")])
            else:
                indented = "\n".join(["    " + l if l.strip() else l for l in content.split("\n")])
                
            parts = file_content.rsplit("};", 1)
            new_file_content = f"{parts[0]}\n{indented}\n" + "};" + f"{parts[1]}"
            with open(write_path, 'w', encoding='utf-8') as f:
                f.write(new_file_content)
            return f"Mission Tactical Success: API '{name}' injected into '{target_name}'."
            
        return f"Error: Insertion point missing in {target_file}"

    @WinyunqAction("Define", "实现函数体逻辑 (CPP 覆盖式写入)", 
                   params=[{"name": "name", "required": True, "doc": "函数名"}, 
                           {"name": "content", "required": True, "doc": "函数体代码段"}])
    def define(self, name, content):
        target_name = self.state.get("target_name")
        if not target_name: return "Error: Must SetTarget before implementation."
        
        cpp_file = self.resolve_file_by_name(target_name, preferred_ext=".cpp")
        if not cpp_file: return f"Error: CPP file for '{target_name}' not found."
        
        write_path = self.get_write_path(cpp_file)
        if not os.path.exists(write_path):
            with open(cpp_file, 'r', encoding='utf-8') as f: file_content = f.read()
        else:
            with open(write_path, 'r', encoding='utf-8') as f: file_content = f.read()

        import re
        # 寻找 ReturnType Class::Name(Params) { ... }
        # 匹配逻辑：匹配到 { 后，替换其内部
        pattern = rf"(\b{target_name}::{name}\b\(.*?\)\s*)\{{(.*?)\}}"
        if re.search(pattern, file_content, re.DOTALL):
            indented_body = "\n".join(["    " + l if l.strip() else l for l in content.split("\n")])
            new_body = f"{{\n{indented_body}\n}}"
            new_file_content = re.sub(pattern, rf"\1{new_body}", file_content, count=1, flags=re.DOTALL)
            with open(write_path, 'w', encoding='utf-8') as f: f.write(new_file_content)
            return f"Mission Tactical Success: Implemented '{name}' in {write_path}"
        
        return f"Error: Could not find definition stub for '{name}' in {cpp_file}"

    @WinyunqAction("Delete", "剥离 API 声明及实现体", 
                   params=[{"name": "name", "required": True, "doc": "要删除的方法名"}])
    def delete(self, name):
        target_name = self.state.get("target_name")
        search_target = target_name if target_name else name
        msg = ""

        # 1. HPP 删除
        hpp_file = self.resolve_file_by_name(search_target, preferred_ext=".hpp")
        if hpp_file:
            w_path = self.get_write_path(hpp_file)
            cur = w_path if os.path.exists(w_path) else hpp_file
            with open(cur, 'r', encoding='utf-8') as f: c = f.read()
            import re
            pattern = rf"(\s*(?:/\*\*(?:(?!\*/).)*\*/|///.*?\n)\s*)?(\s*(?:UPROPERTY|UFUNCTION)\(.*?\)[\s\n]*)?([ \t]*[\w\d_:<>*&]+\s+\b{name}\b[\s\n]*(?:\(.*?\))?;)"
            if re.search(pattern, c, re.DOTALL):
                new_c = re.sub(pattern, "", c, count=1, flags=re.DOTALL)
                with open(w_path, 'w', encoding='utf-8') as f: f.write(new_c)
                msg += "API Deleted from HPP. "

        # 2. CPP 删除
        cpp_file = self.resolve_file_by_name(search_target, preferred_ext=".cpp")
        if cpp_file and target_name:
            w_path = self.get_write_path(cpp_file)
            cur = w_path if os.path.exists(w_path) else cpp_file
            with open(cur, 'r', encoding='utf-8') as f: c = f.read()
            import re
            pattern = rf"\n[\w\d_:<>*&]+\s+\b{target_name}::{name}\b\(.*?\)\s*\{{.*?\}}"
            if re.search(pattern, c, re.DOTALL):
                new_c = re.sub(pattern, "", c, count=1, flags=re.DOTALL).strip()
                with open(w_path, 'w', encoding='utf-8') as f: f.write(new_c)
                msg += "Implementation Deleted from CPP. "

        return msg if msg else f"Error: '{name}' not found for deletion."


    @WinyunqAction("Block", "针对特定代码块进行精细替换", 
                   params=[{"name": "name", "required": True, "doc": "对象名称"}, 
                           {"name": "target", "required": True, "doc": "要被替换的原始代码块"},
                           {"name": "replacement", "required": True, "doc": "替换后的新代码块"}])
    def block(self, name, target, replacement):
        file_path = self.resolve_file_by_name(name)
        if not file_path:
            return f"Error: Target '{name}' not found for block edit."
            
        write_path = self.get_write_path(file_path)
        
        # 如果 Gemini 文件尚不存在，先从原文件复制
        if not os.path.exists(write_path) and os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                data = f.read()
            with open(write_path, 'w', encoding='utf-8') as f:
                f.write(data)
        
        with open(write_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        if target not in content:
            return f"Error: Target block not found in {write_path}"
            
        new_content = content.replace(target, replacement)
        with open(write_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
            
        return f"Mission Tactical Success: Block updated in {write_path}"

    @WinyunqAction("Target", "快捷设定当前操作文件目标", 
                   params=[{"name": "name", "required": True, "doc": "要锚定的对象名称"}])
    def target(self, name):
        self.state["target_name"] = name
        self.save_state(self.state)
        return f"Mission Strategic Update: Target set to '{name}'"

    def _compile_json_to_winyunq_comment(self, data, target_ext=".hpp"):
        """将递归 JSON 协议编译为高密度对齐的 Winyunq 风格代码骨架 (支持 DoxygenStyle 配置驱动的分流与缩进)"""
        # 尝试从 WinyunqCommenter 导入，如果失败则回退到基础宽度计算
        try:
            from WinyunqCommenter import get_visual_width
        except ImportError:
            def get_visual_width(s): return len(s.encode('gbk'))
        style = self.doxygen_style
        tokens = style.get("tokens", {})
        col_align = style.get("column_align", 40)
        block_indent_enabled = style.get("block_comment_indent", True)
        doc_rule = style.get("doc_block_target", "hpp").lower()
        
        # 判定当前渲染是否需要详细 Block 注释
        # 规则: 目标后缀匹配 doc_block_target 配置，或配置为 both
        ext = target_ext.lower().strip(".")
        is_detailed = (doc_rule == "both") or (doc_rule == ext)

        def render_object(obj, indent_level=0):
            obj_type = obj.get("type", "class").lower()
            if obj_type == "method":
                return render_method(obj, indent_level)
                
            indent = "    " * indent_level
            # 缩进策略：若开启 block_indent_enabled，则注释缩进 = 代码缩进；否则为顶格 ("")
            c_indent = indent if block_indent_enabled else ""
            output = []
            
            # 1. 注释渲染分流
            if is_detailed:
                # 输出完整详细的 Block 注释
                output.append(f"{c_indent}/**")
                output.append(f"{c_indent} * {tokens.get('brief', '@brief')}       {obj.get('brief', '')}")
                if obj.get("details"):
                    output.append(f"{c_indent} * {tokens.get('details', '@details')}     {obj.get('details', '')}")
                if obj.get("base"):
                    output.append(f"{c_indent} * {tokens.get('extend', '@extend')} {obj.get('base')}")
                output.append(f"{c_indent} **/")
            else:
                # 仅输出单行精简注释 (作为实现桩的辅助)
                output.append(f"{indent}/// {tokens.get('brief', '@brief')} {obj.get('brief', '')}")
            
            # 2. 对象骨架 (类/结构级别通常只出现在 HPP，但逻辑通用)
            if obj_type == "class":
                output.append(f"{indent}UCLASS()")
                output.append(f"{indent}class {obj['name']} : public {obj.get('base', 'UObject')} {{")
                output.append(f"{indent}    GENERATED_BODY()")
                output.append(f"{indent}public:")
            elif obj_type == "struct":
                output.append(f"{indent}USTRUCT(BlueprintType)")
                output.append(f"{indent}struct {obj['name']} {{")
                output.append(f"{indent}    GENERATED_BODY()")
            
            # 3. 递归处理 Children
            for child in obj.get("children", []):
                c_type = child.get("type", "").lower()
                if c_type in ["class", "struct"]:
                    output.append(render_object(child, indent_level + 1))
                    output.append("")
                elif c_type == "property":
                    output.append(f"{indent}    /// {tokens.get('brief', '@brief')} {child.get('brief', '')}")
                    output.append(f"{indent}    UPROPERTY(EditAnywhere, BlueprintReadWrite)")
                    output.append(f"{indent}    {child['data_type']} {child['name']};")
                    output.append("")
                elif c_type == "method":
                    output.append(render_method(child, indent_level + 1))
                    output.append("")
                    
            if obj_type in ["class", "struct"]:
                output.append(f"{indent}}};")
            return "\n".join(output)

        def render_method(method, indent_level):
            indent = "    " * indent_level
            c_indent = indent if block_indent_enabled else ""
            lines = []
            
            if is_detailed:
                lines.append(f"{c_indent}/**")
                lines.append(f"{c_indent} * {tokens.get('brief', '@brief')}       {method.get('brief', '')}")
                if method.get("details"):
                    lines.append(f"{c_indent} * {tokens.get('details', '@details')}     {method.get('details', '')}")
                
                for p in method.get("params", []):
                    prefix = f"{c_indent} * {tokens.get('param', '@param')}       "
                    line_part1 = f"{prefix}{p['name']}"
                    current_width = get_visual_width(line_part1)
                    padding_len = max(1, col_align - current_width - get_visual_width("数据类型:"))
                    lines.append(f"{line_part1}{' ' * padding_len}数据类型:{p['type']}")
                    if p.get("brief"): lines.append(f"{c_indent} * {tokens.get('details', '@details')}     {p['brief']}")
                lines.append(f"{c_indent} **/")
            else:
                lines.append(f"{indent}/// {tokens.get('brief', '@brief')} {method.get('brief', '')}")
            
            # 仅在 HPP (或非 CPP 环境) 下渲染 UFUNCTION 与 API 签名
            if ext != "cpp":
                lines.append(f"{indent}UFUNCTION(BlueprintCallable)")
                params_str = ", ".join([f"{p['type']} {p['name']}" for p in method.get("params", [])])
                lines.append(f"{indent}{method.get('return_type', 'void')} {method['name']}({params_str});")
            
            return "\n".join(lines)

        return render_object(data)

if __name__ == "__main__":
    tool = WriteCode()
    if "--manifest" in sys.argv:
        print(json.dumps(tool.get_manifest(), ensure_ascii=False))
