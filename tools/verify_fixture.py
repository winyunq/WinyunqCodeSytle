"""Actual portable C++ compilation/cost tests. Not Unreal/UHT validation."""
from pathlib import Path
import argparse
import shutil
import subprocess
import sys
import tempfile
from verify_reuse_count import verify

def main(root):
    code=verify(root)
    if code:return code
    compiler=shutil.which('g++') or shutil.which('clang++')
    with tempfile.TemporaryDirectory(prefix='umm-functions-') as d:
        folder=Path(d);test=folder/'test.cpp'
        extra=''
        if 'A::ClampStep' in (root/'Source/A.cpp').read_text():extra='if(a.ClampStep(-2)!=0||a.ClampStep(300)!=100)return 4;'
        test.write_text('#include "A.h"\nint main(){A a;if(a.Normalize(3)!=3||a.Sibling(3)!=6)return 3;'+extra+'return 0;}')
        exe=folder/('test.exe' if sys.platform=='win32' else 'test')
        p=subprocess.run([compiler,'-std=c++17','-I',str(root/'Source'),str(root/'Source/A.cpp'),str(test),'-o',str(exe)],capture_output=True,text=True,timeout=40)
        if p.returncode:print(p.stderr[-4000:]);return p.returncode
        result=subprocess.run([str(exe)],timeout=10)
        if result.returncode:print('FAIL: A behavior regression')
        else:print('A member declaration/definition compile and runtime assertions: PASS')
        return result.returncode

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--project',type=Path,required=True);a=p.parse_args();sys.exit(main(a.project))
