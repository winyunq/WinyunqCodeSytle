"""Chinese desktop GUI. All project reads/writes call the actual stdio MCP.
Only local-user approval, unlock and recovery use direct trusted callbacks.
"""
from __future__ import annotations
import json
import math
import os
from pathlib import Path
import queue
import shutil
import tempfile
import threading
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
import time
from .client import Client
from .common import encode,sha,canonical
from doxygenue.store import Store

ROOT=Path(__file__).resolve().parents[1]

class App:
    def __init__(self,master,project='',profile='',doxygen='',db=''):
        self.root=master;self.client=None;self.queue=queue.Queue();self.busy=False;self.plan='';self.plan_tool='Write';self.last={}
        self.root.title('UnrealEngineCPPCodingMCP — UE5 C++ 代码 MCP');self.root.geometry('1320x900')
        self.project=tk.StringVar(value=project);self.profile=tk.StringVar(value=profile);self.doxygen=tk.StringVar(value=doxygen);self.db=db
        self.query=tk.StringVar(value='单位');self.name=tk.StringVar();self.path=tk.StringVar();self.view=tk.StringVar(value='auto');self.kind=tk.StringVar(value='data');self.import_file=tk.StringVar()
        self.status=tk.StringVar(value='未连接。选择已有项目与用户批准的维护配置；没有配置则只读。')
        top=ttk.Frame(master,padding=8);top.pack(fill='x')
        for i,(title,var,chooser) in enumerate([('项目',self.project,'dir'),('维护配置',self.profile,'file'),('Doxygen',self.doxygen,'file')]):
            ttk.Label(top,text=title,width=10).grid(row=i,column=0,sticky='w');ttk.Entry(top,textvariable=var).grid(row=i,column=1,sticky='ew',padx=4)
            ttk.Button(top,text='选择',command=lambda v=var,c=chooser:self.choose(v,c)).grid(row=i,column=2)
        top.columnconfigure(1,weight=1)
        bar=ttk.Frame(top);bar.grid(row=0,column=3,rowspan=3,padx=8)
        for label,func in [('连接真实MCP',self.connect),('新建演示副本',self.demo),('内容模式',lambda:self.choose_demo_mode('content')),('代码维护模式',lambda:self.choose_demo_mode('maintain'))]:ttk.Button(bar,text=label,command=func).pack(fill='x')
        ttk.Label(master,textvariable=self.status,wraplength=1260,padding=8).pack(fill='x')
        search=ttk.Frame(master,padding=(8,0));search.pack(fill='x')
        ttk.Label(search,text='搜索现有能力/数据').pack(side='left');ttk.Entry(search,textvariable=self.query,width=44).pack(side='left',padx=5)
        ttk.Combobox(search,textvariable=self.view,values=['auto','brief','overview','details','code','comments','rows','project','changes','history'],width=14,state='readonly').pack(side='left')
        ttk.Button(search,text='搜索/读',command=self.read).pack(side='left',padx=4)
        ttk.Button(search,text='读当前缺省',command=lambda:self.read(True)).pack(side='left')
        ttk.Button(search,text='锁/审批/恢复',command=self.review).pack(side='right')
        loc=ttk.Frame(master,padding=8);loc.pack(fill='x')
        ttk.Label(loc,text='本次名称（可空）').pack(side='left');ttk.Entry(loc,textvariable=self.name,width=43).pack(side='left',padx=4)
        ttk.Label(loc,text='本次路径（可空）').pack(side='left');ttk.Entry(loc,textvariable=self.path,width=47).pack(side='left',padx=4)
        ttk.Button(loc,text='设为缺省',command=lambda:self.send('Configure',{'action':'target',**self.locator()})).pack(side='left')
        self.tabs=ttk.Notebook(master);self.tabs.pack(fill='both',expand=True,padx=8,pady=6)
        reading=ttk.Frame(self.tabs);self.tabs.add(reading,text='读取 / 实际结果')
        self.result=self.text(reading);self.result.pack(fill='both',expand=True)
        edit=ttk.Frame(self.tabs);self.tabs.add(edit,text='增改 / 独立删除')
        options=ttk.Frame(edit,padding=4);options.pack(fill='x')
        ttk.Label(options,text='对象/操作').pack(side='left');ttk.Combobox(options,textvariable=self.kind,values=['data','code','function','comment','include','symbol'],width=12,state='readonly').pack(side='left')
        ttk.Label(options,text='导入源（可空）').pack(side='left',padx=4);ttk.Entry(options,textvariable=self.import_file,width=45).pack(side='left')
        ttk.Button(options,text='增改预览',command=self.preview).pack(side='left',padx=4)
        ttk.Button(options,text='删除预览',command=self.delete).pack(side='left')
        ttk.Button(options,text='提交当前计划',command=self.apply).pack(side='left',padx=4)
        ttk.Label(edit,text='数据：右侧填 rows 数组；填了导入源则右侧填 mapping。注释：右侧填字段对象。代码：左右填旧片段/新片段。函数：右侧只填CPP。').pack(anchor='w',padx=6)
        panes=ttk.Panedwindow(edit,orient='horizontal');panes.pack(fill='both',expand=True)
        l=ttk.Labelframe(panes,text='旧片段 / 要删的记录keys');r=ttk.Labelframe(panes,text='新内容 / rows / mapping / fields')
        panes.add(l,weight=1);panes.add(r,weight=1);self.old=self.text(l);self.old.pack(fill='both',expand=True);self.new=self.text(r);self.new.pack(fill='both',expand=True)
        self.new.insert('1.0','[{"Id":"marine","Health":50}]')
        preview=ttk.Frame(self.tabs);self.tabs.add(preview,text='预览差异 / 函数差异');self.diff=self.text(preview);self.diff.pack(fill='both',expand=True)
        wire=ttk.Frame(self.tabs);self.tabs.add(wire,text='真实请求 / 返回');self.wire=self.text(wire);self.wire.pack(fill='both',expand=True)
        bottom=ttk.Frame(master,padding=8);bottom.pack(side='bottom',before=self.tabs,fill='x')
        for title,func in [('生成网页',lambda:self.send('Configure',{'action':'generate_website'})),('检查源码注释',lambda:self.send('Configure',{'action':'check_comments'})),('Doxygen导出HTML',lambda:self.send('Configure',{'action':'export_docs'})),('执行受信验证',lambda:self.send('Configure',{'action':'validate'})),('当前计划按函数看',lambda:self.send('Read',{'view':'changes','base':'WORKTREE','target':'PLAN','limit':20})),('Codex/Skill配置',self.configuration),('生成UE桥接启动脚本',self.bridge_launcher)]:ttk.Button(bottom,text=title,command=func).pack(side='left',padx=3)
        self.root.after(80,self.pump);self.root.protocol('WM_DELETE_WINDOW',self.close)
    def text(self,parent):return tk.Text(parent,wrap='word',font=('Noto Sans Mono CJK SC' if os.name!='nt' else 'Microsoft YaHei UI',10),undo=True)
    def choose(self,var,mode):
        value=filedialog.askdirectory() if mode=='dir' else filedialog.askopenfilename()
        if value:var.set(value)
    def locator(self):return {k:v for k,v in {'name':self.name.get().strip(),'path':self.path.get().strip()}.items() if v}
    def choose_demo_mode(self,mode):
        if not hasattr(self,'demo_root') or self.project.get()!=str(self.demo_root):
            messagebox.showinfo('维护配置','这两个按钮只切换演示副本的已知配置。真实项目请选择自己的配置，不能套用演示字段。');return
        self.profile.set(str(ROOT/'examples/profiles'/(mode+'.json')));self.connect()
    def demo(self):
        if self.busy:return
        self.demo_root=Path(tempfile.mkdtemp(prefix='UnrealMaintenance-demo-'))/'ExistingProject'
        shutil.copytree(ROOT/'examples/ExistingProject',self.demo_root);self.project.set(str(self.demo_root));self.profile.set(str(ROOT/'examples/profiles/content.json'));self.name.set('');self.path.set('');self.connect()
    def work(self,func,kind='call'):
        if self.busy:return
        self.busy=True;self.status.set('正在调用真实本机MCP…')
        def run():
            try:self.queue.put((kind,True,func()))
            except Exception as e:self.queue.put((kind,False,str(e)))
        threading.Thread(target=run,daemon=True).start()
    def connect(self):
        # Snapshot ALL Tk variables on the UI thread.
        project,profile,doxygen,db=self.project.get(),self.profile.get(),self.doxygen.get(),self.db
        def run():
            if self.client:self.client.close()
            self.client=Client(project,doxygen,db,profile=profile)
            return self.client.call('Configure')
        self.work(run,'connect')
    def send(self,tool,args):
        if not self.client:messagebox.showerror('未连接','请先连接真实MCP。');return
        self.work(lambda:self.client.call(tool,**args),tool)
    def read(self,current=False):
        args={'view':self.view.get()}
        if not current and self.query.get().strip():args['query']=self.query.get().strip()
        else:args.update(self.locator())
        if args['view'] in ('project','history','changes','rows'):args['limit']=20
        self.send('Read',args)
    def preview(self):
        try:
            kind=self.kind.get();args={'kind':kind,**self.locator()};new=self.new.get('1.0','end-1c');old=self.old.get('1.0','end-1c')
            if kind=='data':
                if self.import_file.get().strip():args.update(import_file=self.import_file.get().strip(),mapping=json.loads(new))
                else:args['rows']=json.loads(new)
            elif kind=='comment':args['fields']=json.loads(new)
            else:args.update(old_code=old,new_code=new)
            self.plan_tool='Write';self.send('Write',args)
        except Exception as e:messagebox.showerror('输入错误',str(e))
    def delete(self):
        from tkinter.simpledialog import askstring
        reason=askstring('明确删除','删除什么，为什么？（文字不是批准）')
        if not reason:return
        try:
            kind=self.kind.get();args={'kind':kind,'reason':reason,**self.locator()}
            if kind=='data':args['keys']=json.loads(self.old.get('1.0','end-1c'))
            elif kind!='symbol':args['old_code']=self.old.get('1.0','end-1c')
            self.plan_tool='Delete';self.send('Delete',args)
        except Exception as e:messagebox.showerror('输入错误',str(e))
    def apply(self):
        if not self.plan:messagebox.showerror('无计划','先预览。');return
        self.send(self.plan_tool,{'action':'apply','plan':self.plan})
    def set_text(self,widget,text):widget.delete('1.0','end');widget.insert('1.0',text)
    def pump(self):
        try:
            while True:
                kind,ok,result=self.queue.get_nowait();self.busy=False
                self.last=result if ok else {'error':result}
                self.set_text(self.result,json.dumps(self.last,ensure_ascii=False,indent=2))
                if ok and isinstance(result,dict) and result.get('plan') and result.get('status')=='preview':
                    self.plan=result['plan'];self.plan_tool=kind
                    self.set_text(self.diff,'\n\n'.join(x['diff'] for x in result.get('files',[])) or json.dumps(result,ensure_ascii=False,indent=2));self.tabs.select(2)
                elif ok and result.get('status')=='applied':self.plan='';self.tabs.select(0)
                elif kind=='Read' and ok and 'functions'in result:self.set_text(self.diff,json.dumps(result,ensure_ascii=False,indent=2));self.tabs.select(2)
                else:self.tabs.select(0)
                if self.client and self.client.records:
                    record=self.client.records[-1];self.set_text(self.wire,json.dumps(record,ensure_ascii=False,indent=2))
                    chars=record['response_chars'];mode='完成' if ok else '拒绝/失败'
                    self.status.set(f'{mode} | 往返 {record["roundtrip_ms"]:.1f} ms | 返回 {chars} 字符 | token≈{math.ceil(chars/4)}（粗估；非模型计费值） | 配置：{Path(self.profile.get()).name or "只读"}')
        except queue.Empty:pass
        self.root.after(80,self.pump)
    def review(self):
        if self.busy:return
        if not self.project.get():return
        window=tk.Toplevel(self.root);window.title('本机用户审阅 — 不向MCP开放授权');window.geometry('1050x720')
        box=tk.Listbox(window,height=9);box.pack(fill='x');text=self.text(window);text.pack(fill='both',expand=True)
        from doxygenue import approvals
        from doxygenue.inspection import history,user_restore
        data=[]
        def refresh():
            box.delete(0,'end');data.clear();s=Store(self.db)
            for r in approvals.pending(s,self.project.get()):data.append(('delete',r));box.insert('end','删除审批 '+r['id']+' '+r['status'])
            for r in s.locks(self.project.get()):data.append(('lock',r));box.insert('end','锁 '+r['name'])
            try:
                for r in s.db.execute("SELECT * FROM asset_approvals WHERE root=? AND status='pending'",(canonical(self.project.get()),)):
                    data.append(('asset',dict(r)));box.insert('end','资产删除审批 '+r['id'])
            except Exception:pass
            for p in sorted((s.path.parent/'doxygenue-transactions').glob('*/journal.json'),reverse=True):
                try:
                    r=json.loads(p.read_text());r['id']=p.parent.name
                    if r.get('root')==canonical(self.project.get()) and r.get('status')=='applied':data.append(('restore',r));box.insert('end','恢复事务 '+r['id'])
                except Exception:pass
            s.close()
        def selected(event=None):
            if not box.curselection():return
            t,r=data[box.curselection()[0]];self.set_text(text,json.dumps(r,ensure_ascii=False,indent=2))
        box.bind('<<ListboxSelect>>',selected)
        def act():
            if not box.curselection():return
            t,r=data[box.curselection()[0]]
            prompt={'delete':'批准上述具体删除差异？','lock':'由你本人解锁？','restore':'恢复前字节？当前内容必须仍等于事务后版本。','asset':'批准上述DataTable记录删除？'}[t]
            if not messagebox.askyesno('用户确认',prompt,parent=window):return
            s=Store(self.db)
            try:
                if t=='delete':approvals.user_decide(s,self.project.get(),r['id'],True)
                elif t=='lock':s.user_unlock(r['id'])
                elif t=='restore':user_restore(s,self.project.get(),r['id'])
                else:
                    if r['expires']<time.time():raise ValueError('已过期')
                    s.db.execute("UPDATE asset_approvals SET status='approved' WHERE id=? AND status='pending'",(r['id'],))
                refresh()
            except Exception as e:messagebox.showerror('未执行',str(e),parent=window)
            finally:s.close()
        bar=ttk.Frame(window);bar.pack(fill='x');ttk.Button(bar,text='刷新（含Codex待审批计划）',command=refresh).pack(side='left');ttk.Button(bar,text='审阅后执行所选用户动作',command=act).pack(side='left');refresh()
    def configuration(self):
        command=str(Path(__import__('sys').executable));args=['-u',str(ROOT/'Run.py'),'server','--project',self.project.get(),'--state-db',self.db]
        if self.profile.get():args+=['--profile',self.profile.get()]
        if self.doxygen.get():args+=['--doxygen',self.doxygen.get()]
        text='[mcp_servers.UnrealEngineCPPCodingMCP]\ncommand = '+json.dumps(command)+'\nargs = '+json.dumps(args,ensure_ascii=False)+'\n\n'
        text+='Skill安装命令（不会覆盖已有不同文件）：\n'+command+' "'+str(ROOT/'tools/install_skill.py')+'" --project "'+self.project.get()+'"'
        self.set_text(self.result,text);self.tabs.select(0)
    def bridge_launcher(self):
        if not self.profile.get():messagebox.showerror('缺少配置','先批准配置中的ue_datatable绑定。');return
        home=Path(self.db).parent/'editor'/sha(canonical(self.project.get()).encode())[:20];home.mkdir(parents=True,exist_ok=True)
        script=home/'StartEditorBridge.py'
        script.write_text('import sys\nsys.path.insert(0,'+repr(str(ROOT))+')\nfrom maintenance.bridge import start_editor_bridge\nstart_editor_bridge('+','.join(repr(x) for x in (canonical(self.project.get()),str(home),self.profile.get()))+')\n',encoding='utf-8')
        self.set_text(self.result,'在实际UE编辑器启用 Python Editor Script Plugin 与 Editor Scripting Utilities，结束PIE后，执行这个Python脚本：\n'+str(script)+'\n\n仅对批准的既有DataTable操作；不会添加游戏运行时代码。');self.tabs.select(0)
    def close(self):
        if self.client:self.client.close()
        self.root.destroy()

def main(project='',profile='',doxygen='',db=''):
    root=tk.Tk();app=App(root,project,profile,doxygen,db);root.mainloop()
