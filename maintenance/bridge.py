"""Editor-only file mailbox. No network port, eval, exec or model supplied Python.
An unavailable editor is an error, never a simulated asset or C++ fallback.
"""
from __future__ import annotations
import json
import os
import time
import uuid
from pathlib import Path
from .common import *
from . import records
from doxygenue.doxygen import dump_atomic


def asset_lock_path(root,asset):
    return canonical(Path(root)/'Content'/(asset.removeprefix('/Game/')+'.uasset'))

class BridgeClient:
    def __init__(self,engine,home):
        self.engine=engine;self.home=Path(home)/sha(engine.root.encode())[:20]
        self.home.mkdir(parents=True,exist_ok=True)
    def call(self,action,binding,**payload):
        heartbeat=self.home/'heartbeat.json'
        if not heartbeat.exists() or time.time()-heartbeat.stat().st_mtime>5:
            raise SafeError('UE编辑器未连接。请在UE运行生成的桥接启动脚本；不会虚构资产或改写C++兜底。')
        info=json_load(heartbeat.read_text('utf-8'))
        if info.get('profile')!=self.engine.profile.fingerprint:raise SafeError('编辑器与MCP使用不同维护配置；请重启桥接。')
        id=uuid.uuid4().hex;deadline=time.time()+25
        request={'id':id,'deadline':deadline,'profile':self.engine.profile.fingerprint,'action':action,'binding':binding,**payload}
        dump_atomic(self.home/(id+'.request.json'),request)
        response=self.home/(id+'.response.json')
        while time.time()<deadline+2:
            if response.exists():
                data=json_load(response.read_text('utf-8'))
                if not data.get('ok'):raise SafeError('UE编辑器拒绝：'+str(data.get('error')))
                return data['result']
            time.sleep(.05)
        # Requests have deadlines checked in the editor; in-progress commit can
        # nevertheless have completed. Never retry blindly or report rollback.
        raise SafeError('UE请求超时，状态未知。检查本地回执 '+str(response)+'，不要盲目重复提交。')

class AssetPlan:
    def __init__(self,engine,action,binding,old,new,snapshot,guards,reason):
        self.id=uuid.uuid4().hex[:20];self.action=action;self.kind='asset'
        self.binding=binding;self.old=old;self.new=new;self.snapshot=snapshot
        self.guards=guards;self.reason=reason;self.epoch=engine.store.epoch()
        self.default_target=engine.code.target
        self.locator={'name':binding['name'],'path':binding['path']}
        self.fingerprint=digest({'profile':engine.profile.fingerprint,'old':old,'new':new,'action':action,'epoch':self.epoch,'guards':{p:sha(v) for p,v in guards.items()}})
        engine.store.db.execute('''CREATE TABLE IF NOT EXISTS asset_approvals(id TEXT PRIMARY KEY,root TEXT,session TEXT,digest TEXT,status TEXT,expires REAL,plan TEXT)''')
    def register_approval(self,engine):
        engine.store.db.execute('INSERT INTO asset_approvals VALUES(?,?,?,?,?,?,?)',
            (self.id,engine.root,engine.session,self.fingerprint,'pending',time.time()+600,
             encode({'binding':self.locator,'reason':self.reason,'before':self.old,'after':self.new})))
    def apply(self,engine):
        p=asset_lock_path(engine.root,self.binding['path'])
        with engine.store.transaction():
            engine.profile.assert_current()
            if engine.store.epoch()!=self.epoch or engine.store.blocked('data:'+self.binding['name'],p,all_file=True):raise SafeError('资产已锁定或锁版本变化。')
            for path,raw in self.guards.items():
                if read_bytes(path)!=raw:raise SafeError('导入源/引用在预览后变化。')
            engine._reference_guards(self.binding,self.new,self.action=='Delete')
            if self.action=='Delete':
                r=engine.store.db.execute('SELECT * FROM asset_approvals WHERE id=?',(self.id,)).fetchone()
                if not r or r['status']!='approved' or r['expires']<time.time() or r['root']!=engine.root or r['session']!=engine.session or r['digest']!=self.fingerprint:raise SafeError('资产删除需要本机用户批准该具体差异。')
                engine.store.db.execute("UPDATE asset_approvals SET status='consumed' WHERE id=?",(self.id,))
            receipt=engine.bridge.call('apply',self.binding['name'],expected=self.snapshot['revision'],rows=self.new,operation=self.action,plan=self.id)
        return {'status':'applied','files':[self.binding['path']], 'validation':{'status':'editor_roundtrip_checked'},'receipt':receipt}


def editor_handler(unreal,profile,home,request):
    """Runs ON the UE editor main thread. This function is contract-tested with a test double;
    shipping docs explicitly distinguish those tests from an actual Unreal run.
    """
    if not re.fullmatch(r'[0-9a-f]{32}',request.get('id','')):raise SafeError('请求ID格式错误。')
    if time.time()>request.get('deadline',0):raise SafeError('过期请求，不执行。')
    profile.assert_current()
    if request.get('profile')!=profile.fingerprint:raise SafeError('配置身份不一致。')
    b=profile.find_binding(request.get('binding',''))
    if b.get('format')!='ue_datatable':raise SafeError('不是批准的数据表资产。')
    action=request.get('action')
    if action not in ('read','apply'):raise SafeError('编辑器仅允许读取、应用既有DataTable记录；不执行代码。')
    table=unreal.EditorAssetLibrary.load_asset(b['path'])
    if table is None or not isinstance(table,unreal.DataTable):raise SafeError('资产不存在或不是DataTable。')
    def export():
        text=unreal.DataTableFunctionLibrary.export_data_table_to_json_string(table)
        if not text:raise SafeError('导出真实DataTable失败。')
        value=json_load(text);records.index(value,b);return value
    before=export();revision=digest(before)
    if action=='read':
        struct=unreal.DataTableFunctionLibrary.get_data_table_row_struct(table)
        return {'rows':before,'revision':revision,'row_struct':struct.get_path_name() if struct else None}
    profile.authorize('asset')
    if request.get('expected')!=revision:raise SafeError('DataTable 在预览后变化。')
    package=unreal.EditorAssetLibrary.get_package_for_object(table)
    dirty=unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()
    if package in dirty:raise SafeError('资产有未保存的用户编辑；先由用户保存。')
    # Main-thread bridge is editor-only; never operate during a PIE session.
    if unreal.EditorLevelLibrary.get_game_world() is not None:raise SafeError('请结束Play In Editor后再导入。')
    new=request.get('rows');records.index(new,b)
    for row in new:records.check_row(row,b)
    oldkeys=set(records.index(before,b));newkeys=set(records.index(new,b))
    if request.get('operation')=='Write' and not oldkeys<=newkeys:raise SafeError('Write不能清空或移除既有行。')
    if request.get('operation') not in ('Write','Delete'):raise SafeError('未知操作。')
    if new==before:return {'status':'unchanged'}
    # A round-trip guard catches schema conversion/loss rather than accepting a
    # successful import boolean as proof that all fields survived.
    folder=Path(home)/'asset_journal'/request['id'];folder.mkdir(parents=True)
    dump_atomic(folder/'before.json',before);dump_atomic(folder/'requested.json',new)
    journal={'asset':b['path'],'status':'applying','before_revision':revision}
    dump_atomic(folder/'receipt.json',journal)
    try:
        with unreal.ScopedEditorTransaction('UnrealMaintenance DataTable rows'):
            table.modify()
            if not unreal.DataTableFunctionLibrary.fill_data_table_from_json_string(table,encode(new)):
                raise SafeError('UE填充DataTable失败。')
            if export()!=new:raise SafeError('UE导入归一化改变了请求或未修改字段；拒绝冒充成功。')
            if not unreal.EditorAssetLibrary.save_loaded_asset(table,False):raise SafeError('UE保存资产失败。')
            if export()!=new:raise SafeError('保存后DataTable回读不一致。')
        journal['status']='applied';journal['after_revision']=digest(new)
    except BaseException:
        ok=unreal.DataTableFunctionLibrary.fill_data_table_from_json_string(table,encode(before))
        ok=bool(ok and export()==before and unreal.EditorAssetLibrary.save_loaded_asset(table,False))
        journal['status']='rolled_back' if ok else 'needs_recovery'
        dump_atomic(folder/'receipt.json',journal)
        if not ok:raise SafeError('资产回滚失败；保留现场和before.json，必须人工恢复。')
        raise
    dump_atomic(folder/'receipt.json',journal)
    return {'status':'applied','asset':b['path'],'journal':str(folder/'receipt.json'),'revision':digest(new)}


def start_editor_bridge(root,home,profile_path):
    import unreal
    from .profile import Profile
    root=canonical(root)
    if canonical(unreal.Paths.project_dir())!=root:raise SafeError('当前UE工程不是配置的项目。')
    profile=Profile(root,profile_path);home=Path(home);home.mkdir(parents=True,exist_ok=True)
    global _handle
    try:unreal.unregister_slate_post_tick_callback(_handle)
    except (NameError,Exception):pass
    last=[0.0]
    def tick(delta):
        if time.monotonic()-last[0]<.25:return
        last[0]=time.monotonic()
        dump_atomic(home/'heartbeat.json',{'profile':profile.fingerprint,'engine':unreal.SystemLibrary.get_engine_version(),'time':time.time()})
        # Receipt/incomplete-journal checks also survive editor restarts.
        uncertain=[]
        for p in home.glob('asset_journal/*/receipt.json'):
            try:
                r=json_load(p.read_text('utf-8'))
                if r['status'] not in ('applied','rolled_back'):uncertain.append(str(p))
            except Exception:uncertain.append(str(p))
        for p in sorted(home.glob('*.request.json'))[:4]:
            active=p.with_name(p.name.replace('.request.json','.processing.json'))
            try:p.replace(active)
            except OSError:continue
            req={}
            try:
                req=json_load(active.read_text('utf-8'))
                if uncertain and req.get('action')=='apply':raise SafeError('存在未恢复资产事务：'+uncertain[0])
                result=editor_handler(unreal,profile,home,req)
                response={'ok':True,'result':result}
            except Exception as e:response={'ok':False,'error':str(e)}
            dump_atomic(home/(active.name.replace('.processing.json','.response.json')),response)
    _handle=unreal.register_slate_post_tick_callback(tick)
    unreal.log('UnrealMaintenance: editor-only DataTable bridge started; no gameplay code added.')
    return _handle
