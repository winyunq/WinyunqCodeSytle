import os
import sys

try:
    from WinyunqReadBase import WinyunqReadBase, WinyunqAction
except ImportError:
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from WinyunqReadBase import WinyunqReadBase, WinyunqAction

class ReadCode(WinyunqReadBase):
    """
    侦察支柱 (Read Pillar)
    战术读取：支持去路径化的对象检索与 ReadForEdit。
    """

    @WinyunqAction("List", "快速扫描对象并列出其内部构成 (Taxonomy)", 
                   params=[{"name": "name", "required": False, "doc": "对象名 (支持 A::B 格式)"}])
    def list_objects(self, name=None):
        return self.execute_list(name)

    @WinyunqAction("Declaration", "读取对象的声明 (接口/类型信息)", 
                   params=[{"name": "name", "required": True, "doc": "对象名称"}])
    def read_declaration(self, name):
        return self.execute_declaration(name)

    @WinyunqAction("Definition", "读取对象的完整定义实现 (源码)", 
                   params=[{"name": "name", "required": True, "doc": "对象名称"}])
    def read_definition(self, name):
        return self.execute_read_for_edit(name) # 默认 Definition 即保留注释

    @WinyunqAction("ReadForEdit", "维护性读取：完整读入代码及注释，准备进行修改", 
                   params=[{"name": "name", "required": True, "doc": "对象名称"}])
    def read_for_edit(self, name):
        return self.execute_read_for_edit(name)

    @WinyunqAction("Reference", "检索对象在当前 Working Path 内的所有引用位置", 
                   params=[{"name": "name", "required": True, "doc": "对象名称"}])
    def read_reference(self, name):
        return self.execute_reference(name)

if __name__ == "__main__":
    tool = ReadCode()
    if "--manifest" in sys.argv:
        import json
        print(json.dumps(tool.get_manifest(), ensure_ascii=False))
