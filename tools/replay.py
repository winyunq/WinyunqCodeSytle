"""Three real public-MCP tasks, plus bad-implementation negative controls.
Creates disposable fixtures. Does not operate on the caller's project.
"""
from __future__ import annotations
import argparse
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from maintenance.client import Client
from maintenance.common import sha,encode
from Run import doxygen_path

def run(output,doxygen):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    project=output/'Project';shutil.copytree(ROOT/'examples/ExistingProject',project)
    state=output/'state/state.db';all_records=[];report={'environment':{'python':sys.version.split()[0],'platform':sys.platform,'ue_editor_executed':False},'scenarios':{}}
    def hashes():return {str(p.relative_to(project)):sha(p.read_bytes()) for p in (project/'Source').rglob('*') if p.is_file()}
    def save():
        (output/'MCP-RUN.json').write_text(json.dumps(all_records,ensure_ascii=False,indent=2),encoding='utf-8')
        (output/'RESULTS.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    def expect_error(c,tool,fragment='',**args):
        try:c.call(tool,**args)
        except RuntimeError as e:
            if fragment:assert fragment in str(e),str(e)
            return str(e)
        raise AssertionError('Expected real operation refusal: '+tool)
    c=None
    try:
        c=Client(project,'/intentionally/not/installed',state,profile=ROOT/'examples/profiles/content.json',name='Replay-Content')
        tools=c.rpc('tools/list')['result'];(output/'TOOLS.json').write_text(json.dumps(tools,ensure_ascii=False,indent=2),encoding='utf-8')
        before=hashes();q=c.call('Read',query='单位');overview=c.call('Read',view='overview');baseline=json.loads((project/'Content/Data/Units.json').read_text())
        bad=expect_error(c,'Write','内容维护',kind='function',new_code='void NewAdvisorManager() {}')
        # An unrelated Read must not silently change the current default.
        c.call('Read',name='Advisors',view='overview')
        mapping={'Id':'UnitId','Advisor':'AdvisorId','Name':'DisplayName','Health':'HitPoints','Description':'Text'}
        p=c.call('Write',import_file='Incoming/MapUnits.json',mapping=mapping);assert p['changed_rows']==2
        applied=c.call('Write',action='apply',plan=p['plan']);repeat=c.call('Write',import_file='Incoming/MapUnits.json',mapping=mapping)
        after=json.loads((project/'Content/Data/Units.json').read_text());assert repeat['status']=='unchanged' and hashes()==before
        assert next(x for x in after if x['Id']=='worker')==next(x for x in baseline if x['Id']=='worker')
        assert {x['Id'] for x in after}=={'marine','medic','worker'}
        report['scenarios']['content']={'query':q,'profile_code_refusal':bad,'changed_rows':p['changed_rows'],'repeat':repeat,'runtime_hashes_before':before,'runtime_hashes_after':hashes(),'omitted_row_preserved':True,'doxygen_needed':False}
        # Measure a big file import without pasting the file through the model.
        bulk=[{'Id':'bulk'+str(i),'Advisor':'military','Name':'单位'+str(i),'Health':i,'Description':'批量文本'} for i in range(4000)]
        bulkpath=project/'Incoming/Bulk.json';bulkpath.write_text(json.dumps(bulk,ensure_ascii=False),encoding='utf-8')
        p=c.call('Write',name='Units',import_file='Incoming/Bulk.json',mapping={k:k for k in bulk[0]});wire=c.records[-1]
        assert p['changed_rows']==4000 and len(p['rows'])<=20 and p['full_changes_local']
        report['bulk']={'source_records':4000,'source_chars':len(bulkpath.read_text()),'preview_request_chars':wire['request_chars'],'preview_response_chars':wire['response_chars'],'model_preview_rows':len(p['rows']),'unit':'characters, not model tokens'}
        c.call('Configure',action='abort');all_records+=c.records;c.close();c=None
        if not doxygen:raise RuntimeError('The C++ tasks require real Doxygen. Set DOXYGEN_EXECUTABLE.')
        report['environment']['doxygen']=subprocess.check_output([doxygen,'--version'],text=True).strip()
        # Negative control: merely compiling does NOT reject inefficient behavior.
        control=copy.deepcopy(json.loads((ROOT/'examples/profiles/maintain.json').read_text()))
        control['validation']['commands']=[['{python}','{package}/tools/verify_reuse_count.py','--project','{project}','--compile-only']]
        cp=output/'compile-only.json';cp.write_text(json.dumps(control),encoding='utf-8')
        c=Client(project,doxygen,state,profile=cp,name='Replay-CompileOnly-NegativeControl')
        old='return ExistingSelection.GetSelectedEntitiesView().Num();'
        scan='int n=0; for(int e:ExistingSelection.GetAllEntities()){if(ExistingSelection.IsEntitySelected(e))++n;} return n;'
        p=c.call('Write',name='Fixture::HUD::GetSelectedCount',old_code=old,new_code=scan)
        controlresult=c.call('Write',action='apply',plan=p['plan']);assert controlresult['validation']=='passed'
        all_records+=c.records;c.close();c=None
        measured=subprocess.run([sys.executable,str(ROOT/'tools/verify_reuse_count.py'),'--project',str(project)],capture_output=True,text=True)
        assert measured.returncode!=0
        report['negative_control']={'compile_only':'accepted inefficient scan','task_validation_exit':measured.returncode,'task_output':measured.stdout+measured.stderr}
        # Recovery is itself made through MCP Write, not a direct source overwrite.
        c=Client(project,doxygen,state,profile=ROOT/'examples/profiles/maintain.json',name='Replay-Maintain')
        interface=c.call('Read',query='zero copy selected entities',view='overview')
        assert interface['name']=='Fixture::Selection::GetSelectedEntitiesView'
        p=c.call('Write',name='Fixture::HUD::GetSelectedCount',old_code=scan,new_code=old)
        correct=c.call('Write',action='apply',plan=p['plan']);assert correct['validation']=='passed'
        failures=[]
        for label,replacement,expect in [('world_scan',scan,'zero world membership'),('copy','return ExistingSelection.GetSelectedEntities().Num();','copies'),('stale_cache','static int n=ExistingSelection.GetSelectedEntitiesView().Num(); return n;','stay correct after selection changes')]:
            before=hashes();p=c.call('Write',name='Fixture::HUD::GetSelectedCount',old_code=old,new_code=replacement)
            error=expect_error(c,'Write',expect,action='apply',plan=p['plan']);assert before==hashes()
            failures.append({'case':label,'rejected':error,'all_source_bytes_rolled_back':True})
        report['scenarios']['reuse']={'existing_api':interface,'accepted_implementation':old,'verification':correct['validation'],'negative_cases':failures}
        p=c.call('Write',name='A::Normalize',old_code='return x + 0;',new_code='return x;')
        shorter=c.call('Write',action='apply',plan=p['plan']);assert shorter['validation']=='passed'
        definition='#include <algorithm>\nint A::ClampStep(int x) const { return std::clamp(Normalize(x),0,100); }'
        p=c.call('Write',kind='function',new_code=definition)
        assert {x['file'] for x in p['files']}=={'Source/A.h','Source/A.cpp'}
        functiondiff=c.call('Read',view='changes',target='PLAN')
        applied=c.call('Write',action='apply',plan=p['plan']);assert applied['validation']=='passed'
        assert 'int ClampStep(int x) const;' in (project/'Source/A.h').read_text()
        report['scenarios']['extend_owner']={'cpp_only_input':definition,'plan':p,'function_diff':functiondiff,'validation':applied['validation'],'shorter_edit':shorter['validation']}
        final=subprocess.run([sys.executable,str(ROOT/'tools/verify_fixture.py'),'--project',str(project)],capture_output=True,text=True)
        assert final.returncode==0,final.stdout+final.stderr
        report['final_native_task_output']=final.stdout+final.stderr
        all_records+=c.records;c.close();c=None
        report['status']='passed';save();return report
    except Exception:
        if c:all_records+=c.records
        report['status']='failed';save();raise
    finally:
        if c:c.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output');p.add_argument('--doxygen',default=doxygen_path())
    a=p.parse_args();path=Path(a.output) if a.output else Path(tempfile.mkdtemp(prefix='UnrealMaintenance-replay-'))/'run'
    result=run(path,a.doxygen);print(json.dumps({'status':result['status'],'output':str(path)},ensure_ascii=False))
