"""Automated real Tk + real stdio smoke. Requires a display; captures actual frames.
Pillow is optional for evidence only, never a product runtime dependency.
"""
from pathlib import Path
import argparse
import json
import os
import sys
import tempfile
import time
import tkinter as tk
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from Run import doxygen_path
from maintenance.gui import App

def run(out,doxygen):
    from PIL import ImageGrab,Image
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    folder=Path(tempfile.mkdtemp(prefix='maintenance-gui-evidence-'))
    root=tk.Tk();errors=[];root.report_callback_exception=lambda *a:errors.append(str(a))
    app=App(root,doxygen=doxygen,db=str(folder/'state/state.db'));frames=[];logs=[]
    def wait():
        end=time.monotonic()+180
        while app.busy and time.monotonic()<end:root.update();time.sleep(.025)
        if app.busy:raise AssertionError('GUI operation timeout')
        for _ in range(5):root.update();time.sleep(.06)
        if errors:raise AssertionError(errors)
        return app.last
    def shot(name):
        root.update();p=out/(name+'.png');ImageGrab.grab(bbox=(root.winfo_rootx(),root.winfo_rooty(),root.winfo_rootx()+root.winfo_width(),root.winfo_rooty()+root.winfo_height())).save(p);frames.append(p)
    def text(widget,value):app.set_text(widget,value)
    def send(tool,args):app.send(tool,args);return wait()
    try:
        app.demo();wait();app.query.set('单位');app.view.set('overview');app.read();r=wait();assert r['name']=='Units';shot('01_existing_data')
        app.name.set('');app.path.set('');app.kind.set('data');app.import_file.set('Incoming/MapUnits.json')
        mapping={'Id':'UnitId','Advisor':'AdvisorId','Name':'DisplayName','Health':'HitPoints','Description':'Text'}
        text(app.new,json.dumps(mapping,ensure_ascii=False,indent=2));app.preview();r=wait();assert r['changed_rows']==2;shot('02_record_upsert_preview')
        app.apply();r=wait();assert r['status']=='applied'
        app.kind.set('function');app.import_file.set('');text(app.new,'void NewAdvisorManager() {}');app.preview();r=wait();assert '内容维护'in r['error'];shot('03_content_task_blocks_cpp')
        logs.extend(app.client.records);app.choose_demo_mode('maintain');wait()
        app.query.set('zero copy selected entities');app.view.set('overview');app.read();r=wait();assert r['name']=='Fixture::Selection::GetSelectedEntitiesView';shot('04_existing_api_overview')
        app.name.set('A::Normalize');app.query.set('');app.kind.set('code');text(app.old,'return x + 0;');text(app.new,'return x;')
        app.preview();r=wait();assert r['status']=='preview';app.apply();r=wait();assert r['validation']=='passed'
        app.name.set('');app.path.set('');app.kind.set('function');text(app.old,'');text(app.new,'#include <algorithm>\nint A::ClampStep(int x) const\n{\n    return std::clamp(Normalize(x),0,100);\n}')
        app.preview();r=wait();assert {f['file'] for f in r['files']}=={'Source/A.cpp','Source/A.h'};shot('05_cpp_only_header_preview')
        app.apply();r=wait();assert r['validation']=='passed';shot('06_build_passed')
        app.kind.set('code');app.name.set('Fixture::HUD::GetSelectedCount');text(app.old,'return ExistingSelection.GetSelectedEntitiesView().Num();');text(app.new,'return ExistingSelection.GetSelectedEntities().Num();')
        app.preview();r=wait();app.apply();r=wait();assert 'copies'in r['error'];shot('07_copy_rejected_and_rolled_back')
        app.tabs.select(3);root.update();shot('08_real_rpc')
        logs.extend(app.client.records)
        (out/'GUI-RPC.json').write_text(json.dumps(logs,ensure_ascii=False,indent=2),encoding='utf-8')
        (out/'RESULT.json').write_text(json.dumps({'status':'passed','rpc_requests':len(logs),'tk_errors':errors,'gui':'Linux Tk automated callbacks, not human authentication','ue_editor_executed':False},ensure_ascii=False,indent=2),encoding='utf-8')
        images=[]
        for p in frames:
            im=Image.open(p).convert('RGB');im.thumbnail((1100,750));images.append(im)
        images[0].save(out/'Workflow.gif',save_all=True,append_images=images[1:],duration=2100,loop=0,optimize=True)
        print('GUI passed:',len(logs),'actual RPC requests',out)
    finally:app.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--doxygen',default=doxygen_path());a=p.parse_args();run(a.output,a.doxygen)
