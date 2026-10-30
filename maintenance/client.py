"""Real stdio subprocess client used by the GUI and integration tests."""
from __future__ import annotations
import json
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time

class Client:
    def __init__(self,project,doxygen='',state_db='',name='UnrealMaintenance-GUI',profile='',response_mode='structured'):
        entry=Path(__file__).resolve().parents[1]/'Run.py'
        self.command=([sys.executable,'server','--project',str(project)] if getattr(sys,'frozen',False) else [sys.executable,'-u',str(entry),'server','--project',str(project)])
        if doxygen:self.command+=['--doxygen',str(doxygen)]
        if state_db:self.command+=['--state-db',str(state_db)]
        if profile:self.command+=['--profile',str(profile)]
        self.command+=['--response-mode',response_mode]
        self.process=subprocess.Popen(self.command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        self.responses=queue.Queue();self.stderr=[];self.next_id=0;self.lock=threading.Lock();self.records=[]
        threading.Thread(target=self._reader,daemon=True).start()
        threading.Thread(target=self._errors,daemon=True).start()
        self.rpc('initialize',{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':name,'version':'0.1'}})
        self.notify('notifications/initialized')
    def _reader(self):
        for line in self.process.stdout:
            try:self.responses.put(json.loads(line))
            except Exception:self.responses.put(RuntimeError('MCP stdout 非 JSON'))
        self.responses.put(RuntimeError('MCP已退出：'+'\n'.join(self.stderr[-5:])))
    def _errors(self):
        for line in self.process.stderr:
            self.stderr.append(line.decode('utf-8',errors='replace').rstrip())
            self.stderr[:]=self.stderr[-200:]
    def notify(self,method):
        self.process.stdin.write((json.dumps({'jsonrpc':'2.0','method':method})+'\n').encode());self.process.stdin.flush()
    def rpc(self,method,params=None,timeout=240):
        with self.lock:
            self.next_id+=1;request={'jsonrpc':'2.0','id':self.next_id,'method':method}
            if params is not None:request['params']=params
            wire=json.dumps(request,ensure_ascii=False,separators=(',',':'));start=time.perf_counter()
            self.process.stdin.write(wire.encode()+b'\n');self.process.stdin.flush()
            try:response=self.responses.get(timeout=timeout)
            except queue.Empty:
                self.close();raise TimeoutError('MCP超时并关闭。若此前是提交，请先检查源码与事务日志，不要盲目重试。')
            if isinstance(response,Exception):raise response
            if response.get('id')!=self.next_id:raise RuntimeError('MCP响应id不匹配')
            self.records.append({'request':request,'response':response,'roundtrip_ms':round((time.perf_counter()-start)*1000,3),
                'request_chars':len(wire),'response_chars':len(json.dumps(response,ensure_ascii=False,separators=(',',':'))),
                'request_utf8_bytes':len(wire.encode())})
            return response
    def call(self,tool_name,**arguments):
        response=self.rpc('tools/call',{'name':tool_name,'arguments':arguments})
        if 'error' in response:raise RuntimeError(response['error']['message'])
        result=response['result'];text='\n'.join(x['text'] for x in result.get('content',[]) if x.get('type')=='text')
        if result.get('isError'):raise RuntimeError(text)
        return result['structuredContent'] if 'structuredContent' in result else json.loads(text)
    def close(self):
        p=self.process
        if p.poll() is None:
            try:p.stdin.close();p.wait(timeout=1)
            except Exception:p.kill();p.wait(timeout=2)
        for stream in (p.stdin,p.stdout,p.stderr):
            try:stream.close()
            except Exception:pass
