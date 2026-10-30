"""Native Doxygen source-comment audit and export; no hand-written PDF content."""
from __future__ import annotations
from collections import Counter
from pathlib import Path
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from .cpp import SafeError, canonical, inside, sha, clean_comment, EXTENSIONS
from .doxygen import quote, dump_atomic
from .source_docs import inventory, anchor


def selected_files(engine, path=''):
    cat=engine.catalog;cat.ensure()
    boundary=canonical(Path(engine.root)/path) if path else engine.scope
    if not inside(boundary,engine.scope) or not Path(boundary).exists():raise SafeError('检查/导出范围必须位于当前 scope 内。')
    files=[p for p in cat.scan() if p.suffix.lower() in EXTENSIONS and
           (canonical(p)==boundary if Path(boundary).is_file() else inside(p,boundary))]
    if not files:raise SafeError('所选范围没有 C/C++ 源文件。')
    return files


def run_doxygen(engine,files,folder,*,strict=False,html=False,latex=False,public_only=True):
    cat=engine.catalog;cat.check_binary()
    before={canonical(p):sha(p.read_bytes()) for p in files}
    config=cat.config(files,folder,html)
    config=config.replace('PROJECT_NAME = "DoxygenUnrealEngine"','PROJECT_NAME = '+quote(Path(engine.root).name))
    config=config.replace('EXTRACT_PRIVATE = YES','EXTRACT_PRIVATE = '+('NO' if public_only else 'YES'))
    if strict:
        config=config.replace('EXTRACT_ALL = YES','EXTRACT_ALL = NO')
        config=config.replace('WARN_IF_UNDOCUMENTED = NO','WARN_IF_UNDOCUMENTED = YES')
        config+='WARN_IF_DOC_ERROR = YES\nWARN_IF_INCOMPLETE_DOC = YES\nWARN_NO_PARAMDOC = YES\nWARN_IF_UNDOC_ENUM_VAL = YES\n'
    if latex:
        config=config.replace('GENERATE_LATEX = NO','GENERATE_LATEX = YES')
        style=folder/'DoxygenUECJK.sty'
        style.write_text(r'''\ProvidesPackage{DoxygenUECJK}
\RequirePackage{xeCJK}
\IfFontExistsTF{Noto Serif CJK SC}{\setCJKmainfont{Noto Serif CJK SC}}{\IfFontExistsTF{SimSun}{\setCJKmainfont{SimSun}}{\setCJKmainfont{FandolSong-Regular.otf}}}
\IfFontExistsTF{Noto Sans CJK SC}{\setCJKsansfont{Noto Sans CJK SC}}{\IfFontExistsTF{SimHei}{\setCJKsansfont{SimHei}}{\setCJKsansfont{FandolHei-Regular.otf}}}
\IfFontExistsTF{Noto Sans Mono CJK SC}{\setCJKmonofont{Noto Sans Mono CJK SC}}{\IfFontExistsTF{SimSun}{\setCJKmonofont{SimSun}}{\setCJKmonofont{FandolFang-Regular.otf}}}
''',encoding='utf-8')
        config+='LATEX_CMD_NAME = xelatex\nUSE_PDFLATEX = YES\nLATEX_BATCHMODE = YES\nCOMPACT_LATEX = YES\n'
        config+='LATEX_EXTRA_STYLESHEET = '+quote(str(style))+'\n'
    config+='VERBATIM_HEADERS = NO\nOUTPUT_LANGUAGE = English\nSTRIP_FROM_PATH = '+quote(engine.root)+'\n'
    config+='WARN_LOGFILE = '+quote(str(folder/'warnings.log'))+'\n'
    (folder/'Doxyfile').write_text(config,encoding='utf-8')
    p=subprocess.run([cat.executable,str(folder/'Doxyfile')],cwd=engine.root,
        capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=180,check=False)
    (folder/'process.log').write_text(p.stdout+'\n'+p.stderr,encoding='utf-8')
    if p.returncode or not (folder/'xml/index.xml').exists():raise SafeError(f'Doxygen 失败（{p.returncode}），日志：{folder / "process.log"}')
    if any(not Path(p).exists() or sha(Path(p).read_bytes())!=h for p,h in before.items()):
        raise SafeError('Doxygen 运行期间源码变化；结果作废，请重试。')
    warnings=(folder/'warnings.log').read_text(encoding='utf-8',errors='replace') if (folder/'warnings.log').exists() else ''
    return {'returncode':p.returncode,'warning_count':warnings.lower().count('warning:'),
            'warnings':str(folder/'warnings.log'),'log':str(folder/'process.log'),
            'doxyfile':str(folder/'Doxyfile'),'version':cat.version,'source_hashes':before}


def _problems(engine,e):
    from .quality import semantic_issues
    from .policy import load
    return [code for rule,code in semantic_issues(engine,e,load(engine.store,engine.root))[0]], ''


def check_comments(engine,path='',public_only=True,limit=50,**kwargs):
    from .quality import audit
    return audit(engine,path,public_only,limit,**kwargs)


def export_docs(engine,path='',output_format='html',public_only=True):
    if output_format not in {'html','latex','pdf'}:raise SafeError('仅支持原生 html/latex/pdf 导出。')
    start=time.perf_counter();files=selected_files(engine,path)
    folder=Path(tempfile.mkdtemp(prefix='source-doc-export-',dir=engine.catalog.cache))
    native=run_doxygen(engine,files,folder,html=True,latex=output_format!='html',public_only=public_only)
    result={'publication':'preview','status':'exported','engine':'Doxygen','source_only':True,'format':output_format,
            'files':[os.path.relpath(p,engine.root) for p in files],'native_doxygen':native,
            'html':str(folder/'html/index.html'),'xml':str(folder/'xml'),
            'latex':str(folder/'latex') if output_format!='html' else None,'pdf':None}
    if output_format=='pdf':
        exe=shutil.which('xelatex')
        if not exe:
            result.update(status='pdf_unavailable',message='缺少 XeLaTeX；原生 HTML/LaTeX 已导出。安装 TeX Live 或 MiKTeX 后可在 latex 目录执行 make.bat。')
        else:
            logs=[];ok=True
            cmds=[[exe,'-no-shell-escape','-interaction=nonstopmode','-halt-on-error','refman.tex']]
            indexer=shutil.which('makeindex')
            if indexer:cmds.append([indexer,'refman.idx'])
            cmds+= [cmds[0],cmds[0]]
            try:
                for cmd in cmds:
                    p=subprocess.run(cmd,cwd=folder/'latex',capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=180,check=False)
                    logs.append('$ '+' '.join(cmd)+'\n'+p.stdout+'\n'+p.stderr)
                    if p.returncode:ok=False;break
            except (OSError,subprocess.SubprocessError) as exc:logs.append(str(exc));ok=False
            (folder/'latex-process.log').write_text('\n'.join(logs),encoding='utf-8')
            if ok and (folder/'latex/refman.pdf').exists():result['pdf']=str(folder/'latex/refman.pdf')
            else:result.update(status='pdf_failed',message='Doxygen LaTeX 编译失败；保留原生 HTML、LaTeX 和完整日志，未用另写报告代替 PDF。')
            result['latex_log']=str(folder/'latex-process.log')
            result['tex_diagnostic_log']=str(folder/'latex/refman.log')
    result['elapsed_ms']=round((time.perf_counter()-start)*1000,3)
    dump_atomic(folder/'export.json',result)
    return result
