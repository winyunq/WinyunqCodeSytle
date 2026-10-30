"""Optional fixed Doxygen 1.18.0 Windows runtime. Verify official release digest.
Core data tools do not require it. Source: UPSTREAM.json. Network used only here.
"""
from pathlib import Path
import hashlib
import json
import os
import urllib.request
import zipfile
import tempfile
ROOT=Path(__file__).resolve().parents[1]

def main():
    info=json.loads((ROOT/'UPSTREAM.json').read_text())['windows_runtime']
    if os.name!='nt':raise SystemExit('On non-Windows, select an installed doxygen binary using --doxygen.')
    dest=ROOT/'.runtime/doxygen-1.18.0'
    if dest.exists():raise SystemExit('Runtime directory exists; not overwritten.')
    with tempfile.TemporaryDirectory() as d:
        archive=Path(d)/'doxygen.zip'
        with urllib.request.urlopen(info['url'],timeout=60) as source,archive.open('wb') as sink:
            while chunk:=source.read(1024*1024):sink.write(chunk)
        if hashlib.sha256(archive.read_bytes()).hexdigest()!=info['sha256']:raise RuntimeError('Official SHA256 mismatch; not installed')
        with zipfile.ZipFile(archive) as z:
            if any(Path(i.filename).is_absolute() or '..' in Path(i.filename).parts for i in z.infolist()):raise RuntimeError('Unsafe archive')
            z.extractall(dest)
    print('Doxygen installed:',dest)
if __name__=='__main__':main()
