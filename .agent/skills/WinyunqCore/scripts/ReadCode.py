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
                   params=[{"name": "name", "required": False, "doc": "对象名称；省略时使用当前 Target"}])
    def read_declaration(self, name=None):
        return self.execute_declaration(name)

    @WinyunqAction("Definition", "只读取当前函数的实现代码，并剥离注释与兄弟函数",
                   params=[{"name": "name", "required": False, "doc": "对象名称；省略时使用当前 Target"}])
    def read_definition(self, name=None):
        return self.execute_definition(name)

    @WinyunqAction("ReadForEdit", "只读取当前函数的精确源码并保留其内部注释",
                   params=[{"name": "name", "required": False, "doc": "对象名称；省略时使用当前 Target"}])
    def read_for_edit(self, name=None):
        return self.execute_read_for_edit(name)

    @WinyunqAction("Reference", "检索对象在当前 Working Path 内的所有引用位置", 
                   params=[{"name": "name", "required": False, "doc": "对象名称；省略时使用当前 Target"}])
    def read_reference(self, name=None):
        return self.execute_reference(name)

    @WinyunqAction("Comments", "单独读取当前函数的声明前、定义前和函数体内部注释",
                   params=[
                       {"name": "name", "required": False, "doc": "对象名称；省略时使用当前 Target"},
                       {"name": "part", "required": False, "doc": "body（缺省）、declaration、definition 或 all"}
                   ])
    def read_comments(self, name=None, part="body"):
        return self.execute_comments(name, part)

if __name__ == "__main__":
    tool = ReadCode()
    if "--manifest" in sys.argv:
        import json
        print(json.dumps(tool.get_manifest(), ensure_ascii=False))
