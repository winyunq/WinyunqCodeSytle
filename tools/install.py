"""Standard-library local installer. Requires Python/Tk, does not claim to be Setup.exe.
Creates a new versioned folder; does not modify user projects or existing installs.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import sys
ROOT=Path(__file__).resolve().parents[1]

def install(dest):
    dest=Path(dest).expanduser().resolve()
    if dest==ROOT or ROOT in dest.parents:raise ValueError('Install outside the extracted package')
    manifest=json.loads((ROOT/'MANIFEST.json').read_text('utf-8'))
    for item in manifest['files']:
        relative=Path(item['path'])
        if relative.is_absolute() or '..' in relative.parts:raise ValueError('Invalid payload path')
        p=ROOT/relative
        if p.is_symlink() or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=item['sha256']:raise ValueError('Payload changed: '+item['path'])
    if dest.exists():raise ValueError('Destination exists. Choose a new versioned folder; no overwrite.')
    dest.mkdir(parents=True)
    try:
        for item in manifest['files']:
            p=dest/item['path'];p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/item['path'],p)
        shutil.copyfile(ROOT/'MANIFEST.json',dest/'MANIFEST.json')
    except BaseException:
        shutil.rmtree(dest);raise
    return dest

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--destination',default='');a=parser.parse_args()
    dest=a.destination or str(Path(os.environ.get('LOCALAPPDATA',Path.home()/'.local/share'))/'UnrealEngineCPPCodingMCP/app-0.1.0')
    print('Install to:',dest)
    if not a.destination and input('Type YES to install (projects are untouched): ')!='YES':raise SystemExit('Cancelled')
    print('Installed:',install(dest))
