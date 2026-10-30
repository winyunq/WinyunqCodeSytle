"""One-shot local-user approval of a specific Delete plan.

No approval/confirmation/UNLOCK text is accepted by an MCP tool. The approval
queue is inspectable by the GUI, including plans from another stdio client.
"""
from __future__ import annotations
import difflib
import json
from pathlib import Path
import time
from .cpp import SafeError,canonical,sha,inside
from . import policy


def init(store):
    store.db.execute('''CREATE TABLE IF NOT EXISTS delete_approvals (
        id TEXT PRIMARY KEY, root TEXT NOT NULL, session TEXT NOT NULL,
        digest TEXT NOT NULL, policy_hash TEXT NOT NULL, epoch INTEGER NOT NULL,
        created REAL NOT NULL, expires REAL NOT NULL, status TEXT NOT NULL,
        plan TEXT NOT NULL, approved_at REAL)''')


def plan_digest(plan):
    return policy.digest({'action':plan.action,'kind':plan.kind,'epoch':plan.epoch,'reason':plan.reason,
                          'changes':[(p,None if a is None else sha(a),None if b is None else sha(b)) for p,a,b in plan.changes],
                          'guards':{p:None if b is None else sha(b) for p,b in plan.guards.items()},'locks':plan.locks})


def register(engine):
    init(engine.store);p=engine.plan;rules=policy.load(engine.store,engine.root);now=time.time()
    data={'kind':p.kind,'reason':p.reason,'target':p.locator,'files':[]}
    for path,old,new in p.changes:
        before=(old or b'').decode('utf-8-sig');after=(new or b'').decode('utf-8-sig')
        data['files'].append({'path':path,'before_hash':None if old is None else sha(old),
            'after_hash':None if new is None else sha(new),
            'diff':'\n'.join(difflib.unified_diff(before.splitlines(),after.splitlines(),fromfile=path+' / before',tofile=path+' / after',lineterm=''))})
    with engine.store.transaction():
        engine.store.db.execute("UPDATE delete_approvals SET status='superseded' WHERE root=? AND session=? AND status IN ('pending','approved')",(engine.root,engine.session))
        engine.store.db.execute('INSERT INTO delete_approvals VALUES(?,?,?,?,?,?,?,?,?,?,NULL)',
            (p.id,engine.root,engine.session,plan_digest(p),policy.digest(rules),p.epoch,now,
             now+rules['deletion']['approval_ttl_seconds'],'pending',json.dumps(data,ensure_ascii=False)))
    return {'required':True,'state':'pending','expires_in_seconds':rules['deletion']['approval_ttl_seconds'],
            'instruction':'用户在本机GUI的删除审批页审阅并批准此计划；MCP不存在批准接口。'}


def pending(store,root):
    init(store);now=time.time();rows=[]
    for row in store.db.execute("SELECT * FROM delete_approvals WHERE root=? AND status IN ('pending','approved') ORDER BY created DESC",(canonical(root),)):
        r=dict(row);r['plan']=json.loads(r['plan']);r['status']='expired' if r['expires']<now else r['status'];rows.append(r)
    return rows


def cancel(store,root,session):
    init(store)
    store.db.execute("UPDATE delete_approvals SET status='cancelled' WHERE root=? AND session=? AND status IN ('pending','approved')",(root,session))


def user_decide(store,root,preview_id,approve):
    """LOCAL GUI ONLY; caller has just displayed full diff and asked the person."""
    init(store)
    with store.transaction():
        row=store.db.execute('SELECT * FROM delete_approvals WHERE id=? AND root=?',(preview_id,canonical(root))).fetchone()
        if row is None or row['status'] not in {'pending','approved'}:raise SafeError('删除计划不存在或已结束。')
        if row['expires']<time.time() or row['epoch']!=store.epoch():raise SafeError('删除计划已过期或锁状态变化；重新预览。')
        if row['policy_hash']!=policy.digest(policy.load(store,root)):raise SafeError('用户规则已变化；重新预览。')
        data=json.loads(row['plan'])
        for f in data['files']:
            p=Path(f['path'])
            if not inside(p,root) or canonical(p)!=f['path'] or p.is_symlink():raise SafeError('审批目标路径变化。')
            current=sha(p.read_bytes()) if p.exists() else None
            if current!=f['before_hash']:raise SafeError('审批时源码已变化；重新预览。')
        store.db.execute('UPDATE delete_approvals SET status=?,approved_at=? WHERE id=?',('approved' if approve else 'denied',time.time(),preview_id))
    return {'status':'approved' if approve else 'denied','preview_id':preview_id}


def consume(engine,plan):
    """Called INSIDE the same SQLite transaction as source version/lock checks."""
    row=engine.store.db.execute('SELECT * FROM delete_approvals WHERE id=?',(plan.id,)).fetchone()
    if row is None or row['root']!=engine.root or row['session']!=engine.session or row['status']!='approved':
        raise SafeError('删除尚未获得本机用户对该预览的批准；确认文字不等于批准。请在GUI删除审批页处理。')
    if row['expires']<time.time() or row['epoch']!=engine.store.epoch() or row['digest']!=plan_digest(plan):
        raise SafeError('删除批准已过期或计划/锁变化；重新预览并审批。')
    p=policy.load(engine.store,engine.root)
    if row['policy_hash']!=policy.digest(p):raise SafeError('规则变化使批准失效。')
    if p['deletion']['require_validation'] and plan.kind in {'code','symbol','include'} and not engine.validator:
        raise SafeError('用户规则要求删除前配置构建验证。')
    engine.store.db.execute("UPDATE delete_approvals SET status='consumed' WHERE id=?",(plan.id,))
