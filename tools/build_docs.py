"""Build readable local HTML from the distributed Markdown using stdlib only.
A small renderer for this manual's headings/paragraphs/tables/code; not a general Markdown engine.
"""
from pathlib import Path
import html
import re
ROOT=Path(__file__).resolve().parents[1]
STYLE='''body{font-family:system-ui,"Microsoft YaHei",sans-serif;margin:0;color:#1f2937;background:#f4f6fa;line-height:1.75}main{max-width:1020px;margin:auto;background:white;padding:38px 50px 70px}nav{background:#152a40;color:white;padding:16px 30px}a{color:#146378}nav a{color:white;margin-right:24px}h1{font-size:28px;border-bottom:3px solid #146378;padding-bottom:18px}h2{margin-top:36px;font-size:22px}h3{font-size:18px}pre{overflow:auto;background:#eef3f7;padding:18px;border-left:4px solid #146378;font-size:14px;line-height:1.65}code{font-family:Consolas,monospace;font-size:0.91em}p code{background:#eef3f7;padding:2px 4px}table{border-collapse:collapse;width:100%;margin:18px 0;font-size:14px}th,td{border:1px solid #d4dde5;text-align:left;padding:10px;vertical-align:top}th{background:#eaf2f6}img{max-width:100%}.muted{color:#526577;font-size:14px}.cards{display:grid;grid-template-columns:1fr 1fr;gap:16px}.card{background:#eef3f7;padding:18px;border-radius:5px}@media(max-width:700px){main{padding:22px}.cards{grid-template-columns:1fr}table{font-size:12px}}'''
def inline(text):
    text=html.escape(text)
    text=re.sub(r'`([^`]+)`',r'<code>\1</code>',text)
    text=re.sub(r'\*\*([^*]+)\*\*',r'<b>\1</b>',text)
    text=re.sub(r'\[([^\]]+)\]\(([^)]+)\)',lambda m:'<a href="'+m[2].replace('_ZH.md','_ZH.html').replace('docs/TOOLS.md','docs/TOOLS.html').replace('editor/README.md','editor/README.html')+'">'+m[1]+'</a>',text)
    return text

def render(source):
    lines=source.splitlines();out=[];i=0
    while i<len(lines):
        l=lines[i]
        if l.startswith('```'):
            code=[];i+=1
            while i<len(lines) and not lines[i].startswith('```'):code.append(lines[i]);i+=1
            out.append('<pre><code>'+html.escape('\n'.join(code))+'</code></pre>');i+=1;continue
        if l.startswith('|'):
            rows=[]
            while i<len(lines) and lines[i].startswith('|'):
                if not re.fullmatch(r'[ |:\-]+',lines[i]):rows.append([inline(c.strip()) for c in lines[i].strip('|').split('|')])
                i+=1
            out.append('<table>'+''.join('<tr>'+''.join('<'+('th' if n==0 else 'td')+'>'+c+'</'+('th' if n==0 else 'td')+'>' for c in r)+'</tr>' for n,r in enumerate(rows))+'</table>');continue
        m=re.match(r'^(#{1,4}) (.*)',l)
        if m:out.append(f'<h{len(m[1])}>'+inline(m[2])+f'</h{len(m[1])}>')
        elif l.strip():out.append('<p>'+inline(l.lstrip('- ') if l.startswith('- ') else l)+'</p>')
        i+=1
    return '\n'.join(out)

def page(title,body,prefix):return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+html.escape(title)+'</title><style>'+STYLE+'</style><nav><a href="'+prefix+'index.html">UnrealEngineCPPCodingMCP 0.1.0</a><span>本地使用手册 · 无外部资源</span></nav><main>'+body+'</main></html>'

def build():
    for p in [ROOT/'README.md',*(ROOT/'docs').glob('*.md'),ROOT/'editor/README.md']:
        prefix='' if p.parent==ROOT else '../'
        p.with_suffix('.html').write_text(page(p.stem,render(p.read_text('utf-8')),prefix),encoding='utf-8')
    body='''<h1>UnrealEngineCPPCodingMCP 0.1.0</h1><p>面向 UE5 工程的 C++ 代码 MCP。</p><div class="cards"><section class="card"><h2>开始操作</h2><p>双击 <code>Start-GUI.cmd</code>，点“新建演示副本”；完整自动重放用 <code>Run-Demo.cmd</code>。需要 Python/Tk；数据模式不需要 Doxygen。</p><a href="docs/MANUAL_ZH.html">使用手册</a> · <a href="docs/TOOLS.html">四工具清单</a> · <a href="docs/TOOLS.json">真实 tools/list</a></section><section class="card"><h2>接入你的项目</h2><a href="docs/PROFILE_ZH.html">配置既有数据与验证命令</a> · <a href="docs/WEBSITE_ZH.html">生成定制 Doxygen 网页</a><p><a href="editor/README.html">UE DataTable 编辑器通道</a></p><a href=".agents/skills/ue-maintenance/SKILL.md">Skill</a> · <a href="docs/ACCEPTANCE_ZH.html">可控范围与验收</a></section></div><h2>三个实际结果</h2><table><tr><th>任务</th><th>执行结果</th></tr><tr><td>数据搬运</td><td>一条更新、一条新增；原记录和源码保留；重复导入无变化。内容模式拒绝C++修改。</td></tr><tr><td>复用A</td><td>直接读原选择视图成功。扫描、复制和过期缓存被特定任务断言拒绝并回滚。</td></tr><tr><td>在A中扩展</td><td>只提交CPP，同步H，复用Normalize，实际编译与断言通过。</td></tr></table><p class="muted">以上为实际stdio/Doxygen/原生编译器测试；UE编辑器适配只做API契约测试，未在真实UE、Windows或Codex宿主执行。不是任意架构正确性的自动证明。</p><h2>实际运行记录</h2><p><a href="evidence/replay/RESULTS.json">任务结果</a> · <a href="evidence/replay/MCP-RUN.json">请求/返回</a> · <a href="evidence/TEST_RESULTS.txt">测试</a> · <a href="evidence/Package-Tests.txt">解压复测</a></p><p><a href="evidence/gui/Workflow.gif">实际GUI关键帧动画</a></p><img src="evidence/gui/02_record_upsert_preview.png" alt="实际数据增改预览"><p><a href="NOTICE.md">来源及许可边界</a></p>'''
    (ROOT/'index.html').write_text(page('UnrealEngineCPPCodingMCP',body,''),encoding='utf-8')
if __name__=='__main__':build()
