"""Python 3.10+ entry. Core/data need stdlib; code features require real Doxygen."""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import shutil
import sys

def state_path():
    base=Path(os.environ.get('LOCALAPPDATA') or Path.home()/'.local'/'share')
    return base/'UnrealEngineCPPCodingMCP'/'state.sqlite3'

def doxygen_path(value=''):
    if value:return value
    if os.environ.get('DOXYGEN_EXECUTABLE'):return os.environ['DOXYGEN_EXECUTABLE']
    runtime=Path(__file__).resolve().parent/'.runtime'
    found=list(runtime.glob('**/doxygen.exe' if os.name=='nt' else '**/doxygen'))
    return str(found[0]) if found else shutil.which('doxygen') or ''

def main():
    p=argparse.ArgumentParser(description='UnrealEngineCPPCodingMCP — UE5 C++ coding MCP')
    p.add_argument('mode',nargs='?',default='gui',choices=['gui','server'])
    p.add_argument('--project',default='');p.add_argument('--profile',default='');p.add_argument('--doxygen',default='')
    p.add_argument('--state-db',default='');p.add_argument('--response-mode',default='structured',choices=['structured','text'])
    a=p.parse_args();doxygen=doxygen_path(a.doxygen);db=a.state_db or str(state_path())
    if a.mode=='gui':
        from maintenance.gui import main as gui
        return gui(a.project,a.profile,doxygen,db)
    if not a.project:p.error('server requires --project')
    from doxygenue.store import Store
    from maintenance.engine import Engine
    from maintenance.protocol import Server
    store=Store(db)
    try:Server(Engine(a.project,store,a.profile,doxygen),a.response_mode).run()
    finally:store.close()

if __name__=='__main__':
    if sys.version_info<(3,10):raise SystemExit('CPython 3.10+ is required')
    try:main()
    except KeyboardInterrupt:pass
