"""UE adapter API-contract tests. Test doubles below are NOT an Unreal runtime.
They are never reachable via a product command or the shipping editor bridge.
"""
from __future__ import annotations
import copy
import json
from pathlib import Path
import sys
import tempfile
import time
import types
import unittest
import uuid
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from maintenance.common import SafeError,digest
from maintenance.profile import Profile
from maintenance.bridge import editor_handler,BridgeClient
from maintenance.project import ue_specifiers
from maintenance.records import merge,render,load
from maintenance.protocol import Server

class Table:
    def __init__(self):self.rows=[{'Name':'Marine','Health':45},{'Name':'Worker','Health':30}]
    def modify(self):pass
class Transaction:
    def __init__(self,*a):pass
    def __enter__(self):return self
    def __exit__(self,*a):return False

class EditorContracts(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.table=Table();self.dirty=False;self.pie=False;self.fail=False;self.normalize=False;self.saves=0
        path=self.root/'profile.json';path.write_text(json.dumps({'version':1,'mode':'content','data':[{
            'name':'UnitsAsset','path':'/Game/Data/DT_Units','format':'ue_datatable','key':'Name',
            'fields':{'Name':{'type':'string'},'Health':{'type':'integer'}}}]}))
        self.profile=Profile(self.root,path)
        def fill(table,text):
            rows=json.loads(text);self.table.rows=rows
            if self.fail:self.fail=False;return False
            if self.normalize:rows[0]['Health']+=1;self.normalize=False
            return True
        def save(*args):self.saves+=1;return True
        self.ue=types.SimpleNamespace(DataTable=Table,ScopedEditorTransaction=Transaction,
            DataTableFunctionLibrary=types.SimpleNamespace(export_data_table_to_json_string=lambda t:json.dumps(t.rows),fill_data_table_from_json_string=fill,get_data_table_row_struct=lambda t:types.SimpleNamespace(get_path_name=lambda:'/Script/Game.UnitRow')),
            EditorAssetLibrary=types.SimpleNamespace(load_asset=lambda p:self.table if p=='/Game/Data/DT_Units' else None,get_package_for_object=lambda t:'package',save_loaded_asset=save),
            EditorLoadingAndSavingUtils=types.SimpleNamespace(get_dirty_content_packages=lambda:['package'] if self.dirty else []),
            EditorLevelLibrary=types.SimpleNamespace(get_game_world=lambda:'PIE' if self.pie else None))
    def tearDown(self):self.tmp.cleanup()
    def req(self,action='read',**kwargs):return {'id':uuid.uuid4().hex,'deadline':time.time()+20,'profile':self.profile.fingerprint,'action':action,'binding':'UnitsAsset',**kwargs}
    def runreq(self,r):return editor_handler(self.ue,self.profile,self.root/'bridge',r)
    def test_reads_actual_adapter_rows_and_struct(self):
        result=self.runreq(self.req());self.assertEqual(result['rows'],self.table.rows);self.assertEqual(result['row_struct'],'/Script/Game.UnitRow');self.assertEqual(self.saves,0)
    def test_merge_existing_then_editor_full_fill_preserves_other_rows(self):
        b=self.profile.bindings['UnitsAsset'];new,delta=merge(self.table.rows,[{'Name':'marine','Health':55}],b)
        r=self.runreq(self.req('apply',expected=digest(self.table.rows),rows=new,operation='Write'))
        self.assertEqual(r['status'],'applied');self.assertEqual(self.table.rows,[{'Name':'Marine','Health':55},{'Name':'Worker','Health':30}]);self.assertEqual(self.saves,1)
    def test_empty_fill_is_not_a_write(self):
        with self.assertRaisesRegex(SafeError,'不能清空'):self.runreq(self.req('apply',expected=digest(self.table.rows),rows=[],operation='Write'))
    def test_stale_asset_rejected(self):
        with self.assertRaisesRegex(SafeError,'预览后变化'):self.runreq(self.req('apply',expected='old',rows=[],operation='Delete'))
    def test_unsaved_user_edits_rejected(self):
        self.dirty=True
        with self.assertRaisesRegex(SafeError,'未保存'):self.runreq(self.req('apply',expected=digest(self.table.rows),rows=self.table.rows,operation='Write'))
    def test_pie_rejected(self):
        self.pie=True
        with self.assertRaisesRegex(SafeError,'Play In Editor'):self.runreq(self.req('apply',expected=digest(self.table.rows),rows=self.table.rows,operation='Write'))
    def test_import_failure_restores_before(self):
        self.fail=True;old=copy.deepcopy(self.table.rows);new=copy.deepcopy(old);new[0]['Health']=55
        with self.assertRaisesRegex(SafeError,'填充'):self.runreq(self.req('apply',expected=digest(old),rows=new,operation='Write'))
        self.assertEqual(self.table.rows,old)
        self.assertEqual(json.loads(next((self.root/'bridge').glob('asset_journal/*/receipt.json')).read_text())['status'],'rolled_back')
    def test_silent_conversion_is_not_accepted(self):
        self.normalize=True;old=copy.deepcopy(self.table.rows);new=copy.deepcopy(old);new[0]['Health']=55
        with self.assertRaisesRegex(SafeError,'归一化'):self.runreq(self.req('apply',expected=digest(old),rows=new,operation='Write'))
        self.assertEqual(self.table.rows,old)
    def test_expired_request_and_bad_id(self):
        r=self.req();r['deadline']=time.time()-1
        with self.assertRaisesRegex(SafeError,'过期'):self.runreq(r)
        r=self.req();r['id']='../../outside'
        with self.assertRaisesRegex(SafeError,'ID'):self.runreq(r)
    def test_arbitrary_editor_python_not_exposed(self):
        with self.assertRaisesRegex(SafeError,'仅允许'):self.runreq(self.req('execute_python',code='print("bad")'))
    def test_disconnected_editor_is_error_not_simulation(self):
        client=BridgeClient(types.SimpleNamespace(root=str(self.root),profile=self.profile),self.root/'offline')
        with self.assertRaisesRegex(SafeError,'未连接'):client.call('read','UnitsAsset')

    def test_asset_plan_clears_pending_after_roundtrip_contract(self):
        from maintenance.engine import Engine
        from doxygenue.store import Store
        store=Store(self.root/'state/state.db')
        try:
            e=Engine(self.root,store,self.profile.path,'/no/doxygen')
            e.bridge=types.SimpleNamespace(call=lambda action,binding,**args:self.runreq(self.req(action,**args)))
            p=e.write(name='UnitsAsset',rows=[{'Name':'Marine','Health':66}])
            out=e.write(action='apply',plan=p['plan'])
            self.assertEqual(out['validation'],'editor_roundtrip_checked')
            self.assertIsNone(e.pending);self.assertIsNone(e.code.plan)
            self.assertEqual(self.table.rows[0]['Health'],66)
        finally:store.close()
    def test_asset_delete_needs_separate_local_approval_contract(self):
        from maintenance.engine import Engine
        from doxygenue.store import Store
        store=Store(self.root/'state/state.db')
        try:
            e=Engine(self.root,store,self.profile.path,'/no/doxygen')
            e.bridge=types.SimpleNamespace(call=lambda action,binding,**args:self.runreq(self.req(action,**args)))
            p=e.delete(name='UnitsAsset',keys=['Worker'],reason='explicit test')
            with self.assertRaisesRegex(SafeError,'批准'):e.delete(action='apply',plan=p['plan'])
            # Trusted test callback, intentionally NOT a product MCP operation.
            store.db.execute("UPDATE asset_approvals SET status='approved' WHERE id=?",(p['plan'],))
            out=e.delete(action='apply',plan=p['plan'])
            self.assertEqual(out['status'],'applied');self.assertEqual(len(self.table.rows),1)
            with self.assertRaises(SafeError):e.delete(action='apply',plan=p['plan'])
        finally:store.close()

class StructuralContracts(unittest.TestCase):
    def test_reflection_specifiers_retained(self):
        text='class A {\nUFUNCTION(BlueprintNativeEvent, Category="Test")\nint Count(int X);\nvoid Other();\n};'
        self.assertIn('BlueprintNativeEvent',ue_specifiers(text,3,'Count'));self.assertEqual(ue_specifiers(text,4,'Other'),'')
    def test_nested_metadata_annotation(self):
        text='UFUNCTION(Server, Reliable, meta=(DisplayName="Count"))\nvoid Count();'
        self.assertIn('Reliable',ue_specifiers(text,2,'Count'))
    def test_json_bom_and_untouched_row_bytes(self):
        b={'key':'Id','format':'json','fields':{'Id':{'type':'string'},'Value':{'type':'integer'}}}
        raw=b'\xef\xbb\xbf[\r\n  {"Id":"A", "Value":1},\r\n  {"Id":"B",    "Value":2}\r\n]\r\n'
        out,_=merge(load(raw,'json',b),[{'Id':'A','Value':3}],b);encoded=render(raw,out,b)
        self.assertTrue(encoded.startswith(b'\xef\xbb\xbf'));self.assertIn(b'{"Id":"B",    "Value":2}',encoded);self.assertIn(b'\r\n',encoded)
    def test_nested_object_omissions_survive(self):
        b={'key':'Id','fields':{'Id':{'type':'string'},'Meta':{'type':'object'}}}
        r,_=merge([{'Id':'a','Meta':{'a':1,'b':2}}],[{'Id':'a','Meta':{'a':3}}],b)
        self.assertEqual(r[0]['Meta'],{'a':3,'b':2})
    def test_protocol_rejects_bad_names_without_crashing(self):
        server=Server(None)
        r=server.process({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'clientInfo':'bad'}});self.assertIn('error',r)
        server.process({'jsonrpc':'2.0','id':2,'method':'initialize'})
        r=server.process({'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':[]}});self.assertIn('error',r)
    def test_text_compatibility_does_not_claim_structured_output_schema(self):
        server=Server(None,'text');server.process({'jsonrpc':'2.0','id':1,'method':'initialize'})
        r=server.process({'jsonrpc':'2.0','id':2,'method':'tools/list'})
        self.assertNotIn('outputSchema',r['result']['tools'][0])

if __name__=='__main__':unittest.main(verbosity=2)
