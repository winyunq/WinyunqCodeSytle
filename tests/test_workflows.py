"""Public MCP task tests: no fake server responses, no direct file editing as the solution."""
from __future__ import annotations
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from maintenance.client import Client
from maintenance.common import sha
from doxygenue.store import Store
from doxygenue import approvals
from Run import doxygen_path
DOXYGEN=doxygen_path()

class Workflow(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.folder=Path(self.tmp.name)
        self.project=self.folder/'Project';shutil.copytree(ROOT/'examples/ExistingProject',self.project)
        self.db=self.folder/'state/state.db';self.clients=[]
        self.content=json.loads((ROOT/'examples/profiles/content.json').read_text())
        self.maintain=json.loads((ROOT/'examples/profiles/maintain.json').read_text())
    def tearDown(self):
        for c in self.clients:c.close()
        self.tmp.cleanup()
    def connect(self,profile=None,db=None,doxygen=None):
        path=self.folder/f'profile{len(self.clients)}.json';path.write_text(json.dumps(profile or self.content,ensure_ascii=False))
        c=Client(self.project,DOXYGEN if doxygen is None else doxygen,db or self.db,profile=path)
        self.clients.append(c);return c
    def code_hashes(self):return {str(p.relative_to(self.project)):sha(p.read_bytes()) for p in (self.project/'Source').rglob('*') if p.is_file()}
    def rows(self):return json.loads((self.project/'Content/Data/Units.json').read_text())
    def apply(self,c,tool,**args):
        p=c.call(tool,**args);return c.call(tool,action='apply',plan=p['plan'])
    def test_01_content_import_preserves_runtime_and_omitted_records(self):
        c=self.connect();before=self.code_hashes();old=self.rows()
        hit=c.call('Read',query='单位');self.assertEqual(hit['name'],'Units')
        p=c.call('Write',import_file='Incoming/MapUnits.json',mapping={'Id':'UnitId','Advisor':'AdvisorId','Name':'DisplayName','Health':'HitPoints','Description':'Text'})
        self.assertEqual(p['changed_rows'],2);self.assertFalse(p['runtime_code_changed'])
        c.call('Write',action='apply',plan=p['plan']);out=self.rows()
        self.assertEqual(self.code_hashes(),before);self.assertEqual(out[1],old[1]);self.assertEqual(out[0]['Health'],50);self.assertEqual(out[2]['Id'],'medic')
        original=(self.project/'Content/Data/Units.json').read_bytes()
        p=c.call('Write',import_file='Incoming/MapUnits.json',mapping={'Id':'UnitId','Advisor':'AdvisorId','Name':'DisplayName','Health':'HitPoints','Description':'Text'})
        self.assertEqual(p['status'],'unchanged');self.assertEqual((self.project/'Content/Data/Units.json').read_bytes(),original)
    def test_content_data_works_without_doxygen(self):
        c=self.connect(doxygen='/nonexistent/doxygen')
        self.assertEqual(c.call('Read',query='单位')['name'],'Units')
        self.apply(c,'Write',name='Units',rows=[{'Id':'marine','Health':55}])
        self.assertEqual(self.rows()[0]['Health'],55)
    def test_content_blocks_direct_code_and_new_function(self):
        c=self.connect();before=self.code_hashes()
        for a in ({'name':'A::Normalize','old_code':'return x + 0;','new_code':'return x;'},
                  {'kind':'function','new_code':'int A::DataManager() const {return 1;}'},
                  {'kind':'comment','name':'A::Normalize','fields':{'brief':'绕到注释写入'}}):
            with self.assertRaisesRegex(RuntimeError,'内容维护'):c.call('Write',**a)
        self.assertEqual(self.code_hashes(),before)
    def test_content_cannot_spoof_kind(self):
        c=self.connect()
        for a in ({'kind':'data','path':'Source/A.cpp','rows':[{'Id':'x','new_code':'evil'}]},
                  {'kind':'data','name':'Units','new_code':'int evil();','rows':[{'Id':'marine','Health':9}]}):
            with self.assertRaises(RuntimeError):c.call('Write',**a)
    def test_partial_update_preserves_fields(self):
        c=self.connect();old=self.rows()
        self.apply(c,'Write',name='Units',rows=[{'Id':'marine','Health':66}])
        self.assertEqual(self.rows()[0],{**old[0],'Health':66});self.assertEqual(self.rows()[1],old[1])
    def test_defaults_and_one_call_override(self):
        c=self.connect();c.call('Configure',action='target',name='Units')
        c.call('Read',name='Advisors',view='rows')
        self.apply(c,'Write',rows=[{'Id':'marine','Health':70}])
        self.assertEqual(c.call('Configure')['target']['name'],'Units')
        self.assertEqual(self.rows()[0]['Health'],70)
    def test_two_sessions_have_separate_defaults_and_plans(self):
        c1=self.connect();c2=self.connect();c1.call('Configure',action='target',name='Units');c2.call('Configure',action='target',name='Advisors')
        p=c1.call('Write',rows=[{'Id':'marine','Health':70}])
        with self.assertRaises(RuntimeError):c2.call('Write',action='apply',plan=p['plan'])
        self.assertEqual(c2.call('Configure')['target']['name'],'Advisors')
        c1.call('Write',action='apply',plan=p['plan'])
    def test_no_target_required(self):
        c=self.connect();self.apply(c,'Write',name='Units',rows=[{'Id':'marine','Health':70}]);self.assertIsNone(c.call('Configure')['target'])
    def test_stale_plan_and_source_import_change_rejected(self):
        c=self.connect();p=c.call('Write',name='Units',rows=[{'Id':'marine','Health':70}]);data=self.rows();data[0]['Health']=80
        (self.project/'Content/Data/Units.json').write_text(json.dumps(data))
        with self.assertRaisesRegex(RuntimeError,'变化'):c.call('Write',action='apply',plan=p['plan'])
        p=c.call('Write',name='Units',import_file='Incoming/MapUnits.json',mapping={'Id':'UnitId','Health':'HitPoints','Advisor':'AdvisorId','Name':'DisplayName','Description':'Text'})
        (self.project/'Incoming/MapUnits.json').write_text('[]')
        with self.assertRaisesRegex(RuntimeError,'变化'):c.call('Write',action='apply',plan=p['plan'])
    def test_two_writers_compare_and_swap(self):
        a=self.connect();b=self.connect()
        p=a.call('Write',name='Units',rows=[{'Id':'marine','Health':70}]);q=b.call('Write',name='Units',rows=[{'Id':'marine','Health':80}])
        a.call('Write',action='apply',plan=p['plan'])
        with self.assertRaisesRegex(RuntimeError,'变化'):b.call('Write',action='apply',plan=q['plan'])
        self.assertEqual(self.rows()[0]['Health'],70)
    def test_unknown_type_missing_fields_and_keys_fail(self):
        c=self.connect()
        cases=[[{'Id':'marine','NewField':1}],[{'Id':'marine','Health':True}],[{'Id':'marine','Health':-1}],
               [{'Id':'new','Health':1}],[{'Health':1}],[{'Id':'marine','Health':4},{'Id':'marine','Health':5}]]
        for rows in cases:
            with self.subTest(rows=rows),self.assertRaises(RuntimeError):c.call('Write',name='Units',rows=rows)
    def test_unknown_reference_rejected_not_fabricated(self):
        c=self.connect()
        with self.assertRaisesRegex(RuntimeError,'引用不存在'):c.call('Write',name='Units',rows=[{'Id':'marine','Advisor':'unseen'}])
        self.assertEqual(len(c.call('Read',name='Advisors',view='rows',limit=10)['rows']),2)
    def test_referenced_row_cannot_be_deleted(self):
        c=self.connect()
        with self.assertRaisesRegex(RuntimeError,'引用'):c.call('Delete',name='Advisors',keys=['military'],reason='test')
    def test_delete_difficult_write_cannot_submit_it(self):
        c=self.connect();p=c.call('Delete',name='Units',keys=['worker'],reason='只移除worker')
        with self.assertRaises(RuntimeError):c.call('Write',action='apply',plan=p['plan'])
        with self.assertRaisesRegex(RuntimeError,'批准'):c.call('Delete',action='apply',plan=p['plan'])
        s=Store(self.db);approvals.user_decide(s,str(self.project),p['plan'],True);s.close()
        c.call('Delete',action='apply',plan=p['plan']);self.assertEqual([r['Id'] for r in self.rows()],['marine'])
        with self.assertRaises(RuntimeError):c.call('Delete',action='apply',plan=p['plan'])
    def test_no_approval_or_unlock_rpc(self):
        c=self.connect()
        for a in ('approve','unlock','set','permissions'):
            with self.assertRaises(RuntimeError):c.call('Configure',action=a)
        with self.assertRaises(RuntimeError):c.call('Delete',confirmation='UNLOCK Units')
    def test_lock_shared_scope_cannot_bypass(self):
        c=self.connect();b=self.connect();c.call('Configure',action='lock',name='Units',reason='用户锁')
        b.call('Configure',action='scope',path='Content')
        p=b.call('Write',path='Content/Data/Units.json',rows=[{'Id':'marine','Health':99}])
        with self.assertRaisesRegex(RuntimeError,'锁'):b.call('Write',action='apply',plan=p['plan'])
        s=Store(self.db);s.user_unlock(s.locks(str(self.project))[0]['id']);s.close()
        self.apply(b,'Write',name='Units',rows=[{'Id':'marine','Health':99}])
    def test_changed_profile_invalidates_pending(self):
        c=self.connect();p=c.call('Write',name='Units',rows=[{'Id':'marine','Health':90}])
        path=self.folder/'profile0.json';path.write_text(path.read_text()+' ')
        with self.assertRaisesRegex(RuntimeError,'配置已变化'):c.call('Write',action='apply',plan=p['plan'])
    def test_csv_upsert_quoting_and_newlines(self):
        c=self.connect();p=self.project/'Content/Data/Advisors.csv'
        self.apply(c,'Write',name='Advisors',rows=[{'Id':'civil','Name':'"内政,新"','Description':'一行\n第二行'}])
        out=c.call('Read',name='Advisors',view='rows',limit=10)['rows'];self.assertEqual(out[1]['Name'],'"内政,新"');self.assertIn(b'\r\n',p.read_bytes())
    def test_duplicate_json_keys_fail_in_source(self):
        c=self.connect();(self.project/'Content/Data/Units.json').write_text('[{"Id":"a","Id":"b"}]')
        with self.assertRaisesRegex(RuntimeError,'重复'):c.call('Read',name='Units',view='rows')
    def test_inventory_includes_content_and_ue_dependencies(self):
        c=self.connect();out=c.call('Read',view='project');self.assertGreater(out['counts']['data_or_config'],1)
        self.assertEqual(out['modules'][0]['PublicDependencyModuleNames'],['Core','CoreUObject','Engine'])
        self.assertTrue(any(f['path']=='Content/Data/Units.json' for f in out['files']))
    def test_unknown_data_adapter_is_not_cpp_fallback(self):
        c=self.connect()
        with self.assertRaisesRegex(RuntimeError,'未绑定'):c.call('Write',kind='data',path='Content/Unknown.uasset',rows=[{'Id':'x'}])
    def test_doxygen_unavailable_is_honest(self):
        c=self.connect(doxygen='/no/doxygen')
        r=c.call('Read',query='A::Normalize',kind='code');self.assertEqual(r['results'],[]);self.assertIn('code_index_error',r)
    def test_wire_is_single_structured_and_small(self):
        c=self.connect();r=c.rpc('tools/call',{'name':'Read','arguments':{'query':'单位'}})['result']
        self.assertEqual(r['content'],[]);self.assertIsInstance(r['structuredContent'],dict)
        self.assertNotIn('@brief',json.dumps(r));self.assertLess(len(json.dumps(r,ensure_ascii=False)),350)
    def test_bulk_import_does_not_send_data_back(self):
        c=self.connect();source=[{'Id':str(i),'Advisor':'military','Name':'N'+str(i),'Health':i,'Description':'T'} for i in range(4000)]
        (self.project/'Incoming/Bulk.json').write_text(json.dumps(source))
        p=c.call('Write',name='Units',import_file='Incoming/Bulk.json',mapping={k:k for k in source[0]})
        self.assertEqual(p['changed_rows'],4000);self.assertEqual(len(p['rows']),20);self.assertTrue(p['full_changes_local'])
        c.call('Write',action='apply',plan=p['plan']);self.assertEqual(len(self.rows()),4002)
    def test_preview_apply_payload_cannot_change(self):
        c=self.connect();p=c.call('Write',name='Units',rows=[{'Id':'marine','Health':70}])
        with self.assertRaisesRegex(RuntimeError,'载荷'):c.call('Write',action='apply',plan=p['plan'],rows=[{'Id':'marine','Health':99}])
    def test_read_filter_and_projection(self):
        c=self.connect();r=c.call('Read',name='Units',view='rows',where={'Id':'marine'},fields=['Name','Health'])
        self.assertEqual(r['rows'],[{'Name':'陆战队员','Health':45}])
    @unittest.skipUnless(os.name!='nt','POSIX link probe')
    def test_symlink_import_rejected(self):
        c=self.connect();outside=self.folder/'outside.json';outside.write_text('[]');(self.project/'Incoming/Link.json').symlink_to(outside)
        with self.assertRaisesRegex(RuntimeError,'链接'):c.call('Write',name='Units',import_file='Incoming/Link.json',mapping={'Id':'Id'})
    def test_parent_remembers_data_target(self):
        c=self.connect();c.call('Configure',action='target',name='Units');c.call('Configure',action='parent')
        self.assertIsNone(c.call('Configure')['target']);c.call('Configure',action='child');self.assertEqual(c.call('Configure')['target']['name'],'Units')

@unittest.skipUnless(DOXYGEN,'real Doxygen required; not simulated')
class CodeWorkflow(Workflow):
    # Explicitly limit this class to new tests; inherited tests run in Workflow only.
    def test_header_default_argument_edits_only_declaration(self):
        profile=copy.deepcopy(self.maintain);profile['require_validation']=False;profile.pop('validation',None)
        c=self.connect(profile);cpp=self.project/'Source/A.cpp';original=cpp.read_bytes()
        self.apply(c,'Write',kind='code',operation='modify',name='A::Normalize',path='Source/A.h',
                   part='declaration',old_code='int x',new_code='int x = 1')
        self.assertEqual(cpp.read_bytes(),original)
        self.assertIn('int x = 1',(self.project/'Source/A.h').read_text())

    def test_header_default_argument_cannot_change_parameter_type(self):
        profile=copy.deepcopy(self.maintain);profile['require_validation']=False;profile.pop('validation',None)
        c=self.connect(profile);before=self.code_hashes()
        with self.assertRaisesRegex(RuntimeError,'参数身份和类型保持'):
            c.call('Write',kind='code',name='A::Normalize',path='Source/A.h',part='declaration',
                   old_code='int x',new_code='float x = 1')
        self.assertEqual(self.code_hashes(),before)

    def test_header_default_argument_cannot_cross_declaration(self):
        profile=copy.deepcopy(self.maintain);profile['require_validation']=False;profile.pop('validation',None)
        c=self.connect(profile);before=self.code_hashes()
        with self.assertRaisesRegex(RuntimeError,'指定函数声明内'):
            c.call('Write',kind='code',name='A::Normalize',path='Source/A.h',part='declaration',
                   old_code='int x) const; int Sibling(int x',new_code='int x = 1')
        self.assertEqual(self.code_hashes(),before)

    def test_cpp_default_argument_still_rejected(self):
        profile=copy.deepcopy(self.maintain);profile['require_validation']=False;profile.pop('validation',None)
        c=self.connect(profile);before=self.code_hashes()
        with self.assertRaisesRegex(RuntimeError,'cpp 参数不添加默认值|无法从指定 .cpp 的所属类头文件中唯一定位声明'):
            c.call('Write',kind='code',name='A::Normalize',path='Source/A.cpp',part='definition',
                   old_code='int x',new_code='int x = 1')
        self.assertEqual(self.code_hashes(),before)

    def test_snippet_crosses_comments_inside_one_function(self):
        path=self.project/'Source/A.cpp'
        prefix='#include "A.h"\n\n/// Normalize documentation.\n'
        sibling='\n\n/// Sibling documentation.\nint A::Sibling(int x) const\n{\n    return x * 2;\n}\n'
        path.write_text(prefix+'int A::Normalize(int x) const\n{\n    int value = x;\n    // Removed calculation.\n    value += 0;\n    /* Internal explanation. */\n    return value;\n}'+sibling,encoding='utf-8')
        c=self.connect(self.maintain)
        self.apply(c,'Write',name='A::Normalize',old_code='int value = x; value += 0; return value;',new_code='return x;')
        actual=path.read_text(encoding='utf-8')
        self.assertTrue(actual.startswith(prefix));self.assertTrue(actual.endswith(sibling))
        self.assertIn('return x;',actual);self.assertNotIn('value += 0;',actual)

    def test_comment_update_replaces_explicit_contiguous_block(self):
        from doxygenue.cpp import lex
        path=self.project/'Source/A.cpp'
        block='// Old explanation.\n    // Old second line.\n    // Old third line.\n    // Old fourth line.'
        path.write_text('#include "A.h"\nint A::Normalize(int x) const\n{\n    '+block+'\n    return x + 0;\n}\n',encoding='utf-8')
        profile=copy.deepcopy(self.maintain);profile['require_validation']=False;profile.pop('validation',None)
        c=self.connect(profile);before=[t.value for t in lex(path.read_text())[0]]
        read=c.call('Read',name='A::Normalize',view='comments',part='body')
        comment=next(x for x in read['comments'] if x['text']=='Old explanation.')
        self.apply(c,'Write',kind='comment',name='A::Normalize',part='body',comment_id=comment['comment_id'],
                   old_code=block,new_code='Correct English explanation.\n准确的中文说明。')
        actual=path.read_text(encoding='utf-8')
        self.assertEqual([t.value for t in lex(actual)[0]],before)
        self.assertIn('// Correct English explanation.\n    // 准确的中文说明。',actual)
        self.assertNotIn('Old',actual)

    def test_comment_update_cannot_swallow_code_between_comments(self):
        path=self.project/'Source/A.cpp'
        block='// Old explanation.\n    int value = x;\n    // Old second line.'
        path.write_text('#include "A.h"\nint A::Normalize(int x) const\n{\n    '+block+'\n    return value;\n}\n',encoding='utf-8')
        profile=copy.deepcopy(self.maintain);profile['require_validation']=False;profile.pop('validation',None)
        c=self.connect(profile);before=path.read_bytes()
        read=c.call('Read',name='A::Normalize',view='comments',part='body')
        comment=next(x for x in read['comments'] if x['text']=='Old explanation.')
        with self.assertRaisesRegex(RuntimeError,'连续的行注释'):
            c.call('Write',kind='comment',name='A::Normalize',part='body',comment_id=comment['comment_id'],
                   old_code=block,new_code='Correct explanation.')
        self.assertEqual(path.read_bytes(),before)

    def test_function_replacement_crosses_internal_comments(self):
        path=self.project/'Source/A.cpp'
        prefix='#include "A.h"\n\n/// Normalize documentation.\n'
        sibling='\n\n/// Sibling documentation.\nint A::Sibling(int x) const\n{\n    return x * 2;\n}\n'
        path.write_text(prefix+'int A::Normalize(int x) const\n{\n    int value = x;\n    // Removed calculation.\n    value += 0;\n    /* Internal explanation. */\n    return value;\n}'+sibling,encoding='utf-8')
        c=self.connect(self.maintain)
        self.apply(c,'Write',kind='function',name='A::Normalize',new_code='int A::Normalize(int x) const { return x; }')
        actual=path.read_text(encoding='utf-8')
        self.assertTrue(actual.startswith(prefix));self.assertTrue(actual.endswith(sibling))
        self.assertIn('return x;',actual);self.assertNotIn('value += 0;',actual)

    def test_write_removes_statement_inside_function(self):
        path=self.project/'Source/A.cpp'
        prefix='#include "A.h"\n\n/// Normalize documentation.\n'
        sibling='\n\n/// Sibling documentation.\nint A::Sibling(int x) const\n{\n    return x * 2;\n}\n'
        path.write_text(prefix+'int A::Normalize(int x) const\n{\n    int diagnostic = 0;\n    return x;\n}'+sibling,encoding='utf-8')
        c=self.connect(self.maintain)
        self.apply(c,'Write',kind='code',name='A::Normalize',part='body',old_code='int diagnostic = 0;',new_code='')
        actual=path.read_text(encoding='utf-8')
        self.assertTrue(actual.startswith(prefix));self.assertTrue(actual.endswith(sibling))
        self.assertIn('int A::Normalize(int x) const',actual);self.assertIn('return x;',actual)
        self.assertNotIn('int diagnostic = 0;',actual)

    def test_write_empty_replacement_cannot_clear_function(self):
        path=self.project/'Source/A.cpp'
        original=path.read_bytes();c=self.connect(self.maintain)
        with self.assertRaisesRegex(RuntimeError,'不能清空现有函数体'):
            c.call('Write',kind='code',name='A::Normalize',part='body',old_code='return x + 0;',new_code='')
        self.assertEqual(path.read_bytes(),original)

    def test_write_empty_replacement_cannot_cross_function_boundary(self):
        path=self.project/'Source/A.cpp'
        original=path.read_bytes();c=self.connect(self.maintain)
        with self.assertRaises(RuntimeError):
            c.call('Write',kind='code',name='A::Normalize',part='body',old_code='return x + 0; } int A::Sibling(int x) const { return x * 2;',new_code='')
        self.assertEqual(path.read_bytes(),original)

    def test_edit_cannot_cross_function_boundary(self):
        path=self.project/'Source/A.cpp'
        original=path.read_bytes();c=self.connect(self.maintain)
        with self.assertRaises(RuntimeError):
            c.call('Write',name='A::Normalize',old_code='return x + 0; } int A::Sibling(int x) const { return x * 2;',new_code='return x;')
        self.assertEqual(path.read_bytes(),original)

    def test_function_with_directives_is_editable(self):
        path=self.project/'Source/A.cpp'
        path.write_text('#include "A.h"\n\nint A::Normalize(int x) const\n{\n#pragma region Body\n#define OFFSET 0\n#if 1\n    return x + OFFSET * 0;\n#endif\n#undef OFFSET\n#pragma endregion\n}\n\nint A::Sibling(int x) const\n{\n    return x * 2;\n}\n',encoding='utf-8')
        c=self.connect(self.maintain)
        self.apply(c,'Write',name='A::Normalize',old_code='return x + OFFSET * 0;',new_code='return x * 1 + OFFSET * 0;')
        self.apply(c,'Write',name='A::Normalize',old_code='#define OFFSET 0',new_code='#define OFFSET 1')
        payload='int A::Normalize(int x) const\n{\n#pragma region Body\n#define OFFSET 2\n#if 1\n    return x * 1 + OFFSET * 0;\n#endif\n#undef OFFSET\n#pragma endregion\n}'
        self.apply(c,'Write',kind='function',name='A::Normalize',new_code=payload)
        preview=c.call('Delete',kind='code',name='A::Normalize',old_code='#define OFFSET 2',reason='Verify directive deletion within the located function block')
        self.assertIn('#define OFFSET 2',json.dumps(preview))
        actual=path.read_text(encoding='utf-8')
        self.assertIn('#define OFFSET 2',actual)
        self.assertIn('return x * 1 + OFFSET * 0;',actual)
        self.assertIn('int A::Sibling(int x) const\n{\n    return x * 2;\n}',actual)

    def test_function_inside_unresolved_condition_is_editable(self):
        path=self.project/'Source/Conditional.cpp'
        path.write_text('#if OMIT_FROM_DOXYGEN\nnamespace {\nstruct Hidden {\n    int Run() const { return 2; }\n};\n}\n#endif\n',encoding='utf-8')
        c=self.connect(self.maintain)
        self.apply(c,'Write',name='<anonymous>::Hidden::Run',path='Source/Conditional.cpp',
                   old_code='return 2;',new_code='return 3;')
        actual=path.read_text(encoding='utf-8')
        self.assertIn('return 3;',actual)
        self.assertIn('#if OMIT_FROM_DOXYGEN',actual)
        self.assertIn('#endif',actual)

    def test_explicit_json_tank_paths_only_change_initial_forces(self):
        path=self.project/'Content/Data/StrategicProfiles.json'
        old='/Game/Unit/Actor/Army/Tank/Japan/Old.Old'
        new='/Game/Unit/Actor/Army/Tank/Common/Gen_Common_Old/Old.Old'
        document={'scenarios':[{'scenarioOption':'EastAsia',
                                'initialForces':[{'unitConfig':old},{'unitConfig':old}],
                                'description':'preserved'}]}
        path.write_text(json.dumps(document,ensure_ascii=False,indent=2),encoding='utf-8')
        profile=copy.deepcopy(self.maintain)
        profile['json_path_patch']=['Content/Data/StrategicProfiles.json']
        c=self.connect(profile)
        p=c.call('Write',kind='data',operation='replace_tank_asset_paths',
                 path='Content/Data/StrategicProfiles.json',
                 members=[{'old_code':old,'new_code':new}])
        self.assertEqual(p['changed_paths'][old],2)
        c.call('Write',action='apply',plan=p['plan'])
        actual=json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual([force['unitConfig'] for force in actual['scenarios'][0]['initialForces']],[new,new])
        self.assertEqual(actual['scenarios'][0]['description'],'preserved')

    def test_focus_tank_paths_update_grants_and_history_only(self):
        path=self.project/'Content/Data/Germany1939NationalFocuses.json'
        old='/Game/Unit/Actor/Army/Tank/Germany/MCPGenerated/Germany_Panzer_IV/Germany_Panzer_IV.Germany_Panzer_IV'
        new='/Game/Unit/Actor/Army/Tank/Common/Gen_Common_Tank_Improved/Common_Tank_Improved.Common_Tank_Improved'
        document={'technologies':[{'forceGrants':[{'configAssetPath':old,'onArrivalGrants':[{'configAssetPath':old}]}],
            'historicalMapping':{'historical_formations':[{'game_unit_id':'Germany_Panzer_IV','config_asset_path':old}],
                                 'totals':{'tanks':{'unit_counts':{'Germany_Panzer_IV':1}}}},
            'description':'Preserve description'}]}
        path.write_text(json.dumps(document,ensure_ascii=False,indent=2),encoding='utf-8')
        profile=copy.deepcopy(self.maintain)
        profile['json_path_patch']=['Content/Data/Germany1939NationalFocuses.json']
        c=self.connect(profile)
        p=c.call('Write',kind='data',operation='replace_focus_tank_paths',
                 path='Content/Data/Germany1939NationalFocuses.json',
                 members=[{'old_code':old,'new_code':new}])
        self.assertEqual(p['changed_paths'][old],3)
        c.call('Write',action='apply',plan=p['plan'])
        actual=json.loads(path.read_text(encoding='utf-8'))['technologies'][0]
        self.assertEqual(actual['forceGrants'][0]['configAssetPath'],new)
        self.assertEqual(actual['forceGrants'][0]['onArrivalGrants'][0]['configAssetPath'],new)
        self.assertEqual(actual['historicalMapping']['historical_formations'][0]['game_unit_id'],'Common_Tank_Improved')
        self.assertEqual(actual['historicalMapping']['totals']['tanks']['unit_counts'],{'Common_Tank_Improved':1})
        self.assertEqual(actual['description'],'Preserve description')

    def test_focus_tank_description_updates_only_selected_text(self):
        path=self.project/'Content/Data/NationalFocuses.json'
        old='完成后部署745个步兵团（改进步枪）、14个Germany_Panzer_IV_Ausf_D单位，按各方向预设路线行动。部队完成各自整条路线后才交由玩家控制。'
        new='完成后部署745个步兵团（改进步枪）、14个通用改进型中型坦克单位，按各方向预设路线行动。部队完成各自整条路线后才交由玩家控制。'
        path.write_text(json.dumps({'text':{'focus.germany1939.Barbarossa.description':old,'other':'preserved'}},ensure_ascii=False,indent=2),encoding='utf-8')
        profile=copy.deepcopy(self.maintain)
        profile['json_path_patch']=['Content/Data/NationalFocuses.json']
        c=self.connect(profile)
        p=c.call('Write',kind='data',operation='replace_focus_tank_description',
                 path='Content/Data/NationalFocuses.json',old_code=old,new_code=new)
        c.call('Write',action='apply',plan=p['plan'])
        actual=json.loads(path.read_text(encoding='utf-8'))['text']
        self.assertEqual(actual['focus.germany1939.Barbarossa.description'],new)
        self.assertEqual(actual['other'],'preserved')

    def test_prune_only_legacy_plugin_tank_protocols(self):
        path=self.project/'Plugins/RTSInputSystem/Config/DefaultRTSInputSystem.ini'
        path.parent.mkdir(parents=True,exist_ok=True)
        old=''.join(f'+massUnitTypeProtocols=(SubTypeIndex={i},UnitAssetPath="/Game/Unit/Actor/Army/Tank/Germany/MCPGenerated/Tank_{i}/Tank_{i}.Tank_{i}")\n' for i in range(45))
        path.write_text('[Section]\n+massUnitTypeProtocols=(SubTypeIndex=1,UnitAssetPath="/Game/Unit/Actor/Army/Infantry/Foo.Foo")\n'+old,encoding='utf-8')
        profile=copy.deepcopy(self.maintain)
        profile['ini_tank_protocol_prune']=['Plugins/RTSInputSystem/Config/DefaultRTSInputSystem.ini']
        c=self.connect(profile)
        p=c.call('Delete',kind='data',path='Plugins/RTSInputSystem/Config/DefaultRTSInputSystem.ini',reason='Legacy tank assets were removed')
        self.assertEqual(p['removed_tank_protocols'],45)
        with self.assertRaisesRegex(RuntimeError,'本机用户'):
            c.call('Delete',action='apply',plan=p['plan'])
        self.assertEqual(path.read_text(encoding='utf-8').count('/Game/Unit/Actor/Army/Tank/'),45)

    def test_modify_exact_anonymous_tank_initializers(self):
        source=self.project/'Source/Tanks.cpp'
        old='TEXT("/Game/Unit/Actor/Army/Tank/Germany/Old.Old")'
        new='TEXT("/Game/Unit/Actor/Army/Tank/Common/New.New")'
        source.write_text('namespace {\nconst char* TankPath = '+old+';\nconst int Keep = 7;\n}\n',encoding='utf-8')
        c=self.connect(self.maintain)
        args={'kind':'code','operation':'modify_local_initializers','path':'Source/Tanks.cpp',
              'members':[{'name':'TankPath','old_code':old,'new_code':new}]}
        p=c.call('Write',**args)
        self.assertIn(new,p['files'][0]['diff'])
        c.call('Write',action='apply',plan=p['plan'])
        self.assertEqual(source.read_text(encoding='utf-8'),
                         'namespace {\nconst char* TankPath = '+new+';\nconst int Keep = 7;\n}\n')
        with self.assertRaisesRegex(RuntimeError,'旧值'):
            c.call('Write',**args)

    def test_smoke_default_tank_target_changes_only_literal(self):
        source=self.project/'Source/Winyunq/Private/Tests/WinyunqRTSCommandRuntimeSmoke.cpp'
        source.parent.mkdir(parents=True,exist_ok=True)
        old='TEXT("/Game/Unit/Actor/Army/Tank/Common/Gen_Common_MediumTank_LowPoly/Common_MediumTank_LowPoly.Common_MediumTank_LowPoly")'
        new='TEXT("/Game/Unit/Actor/Army/Tank/Common/Gen_Common_Tank_AdvancedModel_Handpainted/Common_Tank_AdvancedModel_Handpainted.Common_Tank_AdvancedModel_Handpainted")'
        source.write_text('struct FRTSMoveSmokeState { bool Tick() { FString TargetPath = '+old+'; return true; } };\n',encoding='utf-8')
        c=self.connect(self.maintain)
        p=c.call('Write',kind='code',operation='modify_smoke_tank_target',
                 path='Source/Winyunq/Private/Tests/WinyunqRTSCommandRuntimeSmoke.cpp',
                 old_code=old,new_code=new)
        c.call('Write',action='apply',plan=p['plan'])
        self.assertIn(new,source.read_text(encoding='utf-8'))
        self.assertNotIn(old,source.read_text(encoding='utf-8'))

    def test_add_definition_for_unique_namespace_declaration(self):
        header=self.project/'Source/Nation.h'
        source=self.project/'Source/Nation.cpp'
        header.write_text('#pragma once\nnamespace Nation { int Resolve(int value); }\n',encoding='utf-8')
        source.write_text('#include "Nation.h"\n#if 0\n#endif\n',encoding='utf-8')
        c=self.connect(self.maintain)
        payload='namespace Nation { int Resolve(int value) { return value + 1; } }'
        p=c.call('Write',operation='add_symbol',path='Source/Nation.cpp',new_code=payload)
        self.assertEqual(p['added_symbol'],'Nation::Resolve')
        c.call('Write',action='apply',plan=p['plan'])
        self.assertIn('return value + 1;',source.read_text(encoding='utf-8'))
        with self.assertRaisesRegex(RuntimeError,'符号已经存在'):
            c.call('Write',operation='add_symbol',path='Source/Nation.cpp',new_code=payload)

    def test_class_documentation_is_not_constructor(self):
        p=self.project/'Source/A.h'
        p.write_text(p.read_text(encoding='utf-8').replace('public:', 'public:\n    A();'),encoding='utf-8')
        c=self.connect(self.maintain)
        result=c.call('Read',name='A',view='documentation')
        self.assertEqual(result['kind'],'class')
        self.assertEqual(result['name'],'A')
        self.assertIn('不保存另一份输入状态',result['documentation']['brief'])

    def test_edit_shorter_and_siblings_preserved(self):
        c=self.connect(self.maintain);p=self.project/'Source/A.cpp';old=p.read_text()
        self.apply(c,'Write',name='A::Normalize',old_code='return x + 0;',new_code='return x;')
        self.assertEqual(p.read_text(),old.replace('return x + 0;','return x;'))
    def test_cpp_only_member_syncs_header_compiles(self):
        c=self.connect(self.maintain)
        p=c.call('Write',kind='function',new_code='#include <algorithm>\nint A::ClampStep(int x) const { return std::clamp(Normalize(x),0,100); }')
        self.assertEqual({f['file'] for f in p['files']},{'Source/A.cpp','Source/A.h'})
        self.assertEqual(c.call('Write',action='apply',plan=p['plan'])['validation'],'passed')
        self.assertIn('int ClampStep(int x) const;', (self.project/'Source/A.h').read_text())
    def test_existing_api_search_across_name_and_docs(self):
        c=self.connect(self.maintain);r=c.call('Read',query='zero copy selected entities',view='overview')
        self.assertEqual(r['name'],'Fixture::Selection::GetSelectedEntitiesView');self.assertIn('returns',r)
    def test_wasteful_scan_fails_and_rolls_back(self):
        c=self.connect(self.maintain);before=self.code_hashes()
        p=c.call('Write',name='Fixture::HUD::GetSelectedCount',old_code='return ExistingSelection.GetSelectedEntitiesView().Num();',new_code='int n=0; for(int e:ExistingSelection.GetAllEntities()){if(ExistingSelection.IsEntitySelected(e))++n;} return n;')
        with self.assertRaisesRegex(RuntimeError,'zero world membership'):c.call('Write',action='apply',plan=p['plan'])
        self.assertEqual(before,self.code_hashes())
    def test_duplicate_copy_fails_and_rolls_back(self):
        c=self.connect(self.maintain);before=self.code_hashes()
        p=c.call('Write',name='Fixture::HUD::GetSelectedCount',old_code='return ExistingSelection.GetSelectedEntitiesView().Num();',new_code='return ExistingSelection.GetSelectedEntities().Num();')
        with self.assertRaisesRegex(RuntimeError,'copies'):c.call('Write',action='apply',plan=p['plan'])
        self.assertEqual(before,self.code_hashes())
    def test_stale_cache_fails_and_rolls_back(self):
        c=self.connect(self.maintain);before=self.code_hashes()
        p=c.call('Write',name='Fixture::HUD::GetSelectedCount',old_code='return ExistingSelection.GetSelectedEntitiesView().Num();',new_code='static int Cached=ExistingSelection.GetSelectedEntitiesView().Num(); return Cached;')
        self.assertTrue(p['review_signals'])
        with self.assertRaisesRegex(RuntimeError,'FAIL'):c.call('Write',action='apply',plan=p['plan'])
        self.assertEqual(before,self.code_hashes())
    def test_invalid_cpp_rolls_back_header_and_cpp(self):
        c=self.connect(self.maintain);before=self.code_hashes()
        p=c.call('Write',kind='function',new_code='int A::Broken(int x) const { return UnknownFunction(x); }')
        with self.assertRaisesRegex(RuntimeError,'失败'):c.call('Write',action='apply',plan=p['plan'])
        self.assertEqual(before,self.code_hashes())
    def test_user_forbidden_mechanism_blocks_at_preview(self):
        c=self.connect(self.maintain);before=self.code_hashes()
        with self.assertRaisesRegex(RuntimeError,'维护约定'):c.call('Write',name='A::Normalize',old_code='return x + 0;',new_code='SetTimer(); return x;')
        self.assertEqual(before,self.code_hashes())
    def test_source_comment_field_preserves_non_comment_tokens(self):
        from doxygenue.cpp import lex
        c=self.connect(self.maintain);p=self.project/'Source/A.h';before=[t.value for t in lex(p.read_text())[0]]
        self.apply(c,'Write',kind='comment',name='A::Normalize',fields={'brief':'只修改归一化接口的简单说明。'})
        self.assertEqual(before,[t.value for t in lex(p.read_text())[0]])
        self.assertIn('@param x',p.read_text());r=c.call('Read',name='A::Normalize',view='brief');self.assertIn('只修改',r['brief'])
    def test_function_diff_plan(self):
        c=self.connect(self.maintain);c.call('Write',name='A::Normalize',old_code='return x + 0;',new_code='return x;')
        r=c.call('Read',view='changes',base='WORKTREE',target='PLAN',limit=20)
        self.assertIn('A::Normalize',json.dumps(r,ensure_ascii=False))
    def test_no_full_file_fallback(self):
        c=self.connect(self.maintain)
        with self.assertRaises(RuntimeError):c.call('Read',name='A::NotThere',view='raw')
    def test_required_validation_cannot_be_omitted(self):
        config=copy.deepcopy(self.maintain);config.pop('validation');c=self.connect(config)
        with self.assertRaisesRegex(RuntimeError,'真实验证'):c.call('Write',name='A::Normalize',old_code='return x + 0;',new_code='return x;')
    def test_pinned_checks_cannot_be_modified_by_model(self):
        cfg=copy.deepcopy(self.maintain);cfg['pinned_files']=['README.md'];c=self.connect(cfg)
        p=c.call('Write',name='A::Normalize',old_code='return x + 0;',new_code='return x;')
        (self.project/'README.md').write_text('tampered')
        with self.assertRaisesRegex(RuntimeError,'受信'):c.call('Write',action='apply',plan=p['plan'])

# unittest inheritance would otherwise double-count all data tests as code tests.
for _n in list(Workflow.__dict__):
    if _n.startswith('test_') and _n not in CodeWorkflow.__dict__:setattr(CodeWorkflow,_n,None)

if __name__=='__main__':unittest.main(verbosity=2)
