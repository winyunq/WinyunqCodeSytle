"""Explicit local installation; no config overwrite and no silent replacement."""
from pathlib import Path
import argparse
import shutil
import sys
ROOT=Path(__file__).resolve().parents[1]

def install(project):
    project=Path(project).resolve()
    if not project.is_dir():raise ValueError('Project does not exist')
    source=ROOT/'.agents/skills/ue-maintenance';dest=project/'.agents/skills/ue-maintenance'
    changes=[]
    for p in source.rglob('*'):
        if not p.is_file():continue
        target=dest/p.relative_to(source)
        walk=target
        while walk!=project:
            if walk.is_symlink():raise ValueError('Refusing symlink install path')
            walk=walk.parent
        if target.exists() and target.read_bytes()!=p.read_bytes():raise ValueError('Local skill differs; refused before writing: '+str(target))
        if not target.exists():changes.append((p,target))
    for p,target in changes:target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
    return {'installed_files':len(changes),'path':str(dest)}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--project',required=True);a=p.parse_args();print(install(a.project))
