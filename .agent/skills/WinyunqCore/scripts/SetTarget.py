import os
import sys
import json
try:
    from WinyunqBase import WinyunqBase, WinyunqAction
except ImportError:
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from WinyunqBase import WinyunqBase, WinyunqAction

class SetTarget(WinyunqBase):
    """
    战略支柱 (Setting Pillar)
    管辖范围：工作路径、过滤规则、当前状态。
    """
    
    @WinyunqAction("Status", "查看当前战略设定状态 (Scope, Filters, etc.)", params=[])
    def show_status(self):
        combined = {**self.state, "settings": self.settings}
        return json.dumps(combined, indent=4, ensure_ascii=False)

    @WinyunqAction("Path", "修改工作路径 (战略锚点)", 
                   params=[{"name": "path", "required": True, "doc": "新的工作路径 (相对或绝对)"}])
    def change_path(self, path):
        full_path = os.path.abspath(path)
        if not os.path.exists(full_path):
            return f"Error: Path '{full_path}' does not exist."
            
        self.state["work_path"] = full_path
        self.save_state(self.state)
        return f"Strategy Updated: Working Path is now {full_path}"

    @WinyunqAction("Filter", "配置搜索过滤规则", 
                   params=[{"name": "exclude", "required": True, "doc": "过滤模式 (如 *.tmp;node_modules;bin)"}])
    def set_filters(self, exclude):
        filters = [f.strip() for f in exclude.split(";") if f.strip()]
        self.state["filters"] = filters
        self.save_state(self.state)
        return f"Strategy Updated: Filters set to {filters}"

    @WinyunqAction("Target", "设置后续读取与写入所使用的缺省代码对象",
                   params=[{"name": "name", "required": True, "doc": "类、函数或变量名称"}])
    def set_target(self, name):
        self.state["target_name"] = name
        self.save_state(self.state)
        return f"Strategy Updated: Target is now '{name}'"

if __name__ == "__main__":
    tool = SetTarget()
    if "--manifest" in sys.argv:
        print(json.dumps(tool.get_manifest(), ensure_ascii=False))
