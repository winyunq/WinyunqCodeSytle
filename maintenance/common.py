from __future__ import annotations
import hashlib
import json
import os
import re
from pathlib import Path
from doxygenue.cpp import SafeError, canonical, inside, sha

MAX_FILE = 16 * 1024 * 1024
EXCLUDE = {'.git','.svn','.vs','Binaries','DerivedDataCache','Intermediate','Saved','__pycache__','node_modules','.runtime'}

def json_load(raw):
    def pairs(items):
        d = {}
        for k,v in items:
            if k in d: raise SafeError('重复 JSON 键：' + k)
            d[k] = v
        return d
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda x: (_ for _ in ()).throw(SafeError('非法数值：'+x)))

def encode(value):
    return json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False)

def digest(value):
    return sha(encode(value).encode('utf-8'))

def path_in(root, relative, must_exist=True):
    if not isinstance(relative,str) or not relative or '\x00' in relative: raise SafeError('需要项目内相对路径。')
    p = Path(relative)
    if p.is_absolute() or '..' in p.parts or re.match(r'^[A-Za-z]:',relative): raise SafeError('路径必须位于项目内。')
    p = Path(root) / p
    walk = p
    while walk != Path(root):
        if walk.is_symlink(): raise SafeError('拒绝符号链接路径。')
        walk = walk.parent
    if not inside(p,root): raise SafeError('路径越界。')
    if must_exist and not p.is_file(): raise SafeError('文件不存在：'+relative)
    if p.exists() and p.is_file() and p.stat().st_nlink != 1: raise SafeError('拒绝硬链接文件。')
    return p

def read_bytes(p):
    p = Path(p)
    if p.stat().st_size > MAX_FILE: raise SafeError('单文件超过16 MiB，本适配器拒绝而不是截断后写回。')
    return p.read_bytes()

def files(root):
    """Content stays visible. No source-code-only inventory."""
    for folder, dirs, names in os.walk(root,followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDE and not (Path(folder)/d).is_symlink())
        for name in sorted(names):
            p=Path(folder)/name
            if not p.is_symlink() and p.is_file(): yield p

def tokens(text):
    text = re.sub(r'([a-z0-9])([A-Z])',r'\1 \2',text)
    return re.findall(r'[a-z0-9]+|[\u3400-\u9fff]+',text.casefold())
