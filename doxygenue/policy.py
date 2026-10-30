"""Trusted policy snapshots. Only a local user action can import/replace policy.

MCP may inspect the policy, never weaken it or reset the accepted issue baseline.
This is an application boundary, not OS isolation from the same user's shell.
"""
from __future__ import annotations
import copy
import fnmatch
import json
import time
from pathlib import Path
from .cpp import SafeError, canonical, sha

RULES = ('brief', 'params', 'tparams', 'returns', 'details', 'local_comment',
         'placeholder', 'format', 'parameter_names', 'duplicates', 'resolution')
DEFAULT = {
    'schema_version': 1,
    'name': '默认维护规则',
    'rules': {k: ('off' if k in {'details', 'format'} else 'error') for k in RULES},
    'overrides': [],
    'exemptions': [],
    'allow_shared_documentation': True,
    'native_warnings': 'warning',
    'index': {'exclude': [], 'defines': []},
    'release': {'mode': 'no_new_errors', 'public_only': True,
                'require_validation': True, 'block_warnings': False},
    'deletion': {'approval_ttl_seconds': 600, 'require_validation': False}
}
# Parsed/inherited docs are valid by default; enforce local comments when desired.
DEFAULT['rules']['local_comment'] = 'off'


def digest(data):
    return sha(json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode())


def key(root, suffix):
    return 'project:' + sha(canonical(root).encode()) + ':' + suffix


def metadata(store, root, suffix):
    row = store.db.execute('SELECT value FROM metadata WHERE key=?', (key(root, suffix),)).fetchone()
    return json.loads(row[0]) if row else None


def put(store, root, suffix, data):
    store.db.execute('INSERT OR REPLACE INTO metadata(key,value) VALUES(?,?)',
                     (key(root, suffix), json.dumps(data, ensure_ascii=False)))


def validate_policy(data):
    if not isinstance(data, dict) or set(data) - set(DEFAULT):
        raise SafeError('规则只能使用文档中列出的 policy 字段。')
    p = copy.deepcopy(DEFAULT)
    for k, v in data.items():
        if isinstance(p[k], dict) and isinstance(v, dict): p[k].update(v)
        else: p[k] = copy.deepcopy(v)
    if p['schema_version'] != 1 or not isinstance(p['name'], str):
        raise SafeError('规则版本或名称无效。')
    def severities(r):
        if not isinstance(r, dict) or set(r)-set(RULES) or any(v not in {'off','warning','error'} for v in r.values()):
            raise SafeError('规则严重度只能为 off/warning/error。')
    severities(p['rules'])
    if type(p['allow_shared_documentation']) is not bool or p['native_warnings'] not in {'off','warning','error'}:
        raise SafeError('文档共享或原生警告策略无效。')
    if not isinstance(p['overrides'], list) or len(p['overrides']) > 100:
        raise SafeError('overrides 应为不超过100项的列表。')
    for r in p['overrides']:
        if not isinstance(r, dict) or set(r)-{'path','name','visibility','kinds','rules'}: raise SafeError('override 字段无效。')
        severities(r.get('rules', {}))
        for k in ('path','name'):
            if k in r and (not isinstance(r[k],str) or len(r[k])>500): raise SafeError('规则匹配值无效。')
        for k in ('visibility','kinds'):
            if k in r and (not isinstance(r[k],list) or any(not isinstance(x,str) for x in r[k])): raise SafeError('规则匹配列表无效。')
    if not isinstance(p['exemptions'],list) or len(p['exemptions']) > 1000: raise SafeError('exemptions 无效。')
    for e in p['exemptions']:
        if not isinstance(e,dict) or set(e)-{'path','name','rule','reason','expires'}: raise SafeError('豁免字段无效。')
        if e.get('rule') not in RULES or not isinstance(e.get('reason'),str) or not e['reason'].strip(): raise SafeError('豁免必须有准确规则和理由。')
        for k in ('path','name'):
            if k in e and not isinstance(e[k],str): raise SafeError('豁免匹配值无效。')
        if 'expires' in e:
            from datetime import date
            try: date.fromisoformat(e['expires'])
            except (TypeError,ValueError): raise SafeError('expires 使用 YYYY-MM-DD。')
    from .doxygen import Catalog
    if not isinstance(p['index'],dict) or set(p['index']) != {'exclude','defines'}: raise SafeError('policy.index 仅接受 exclude/defines。')
    Catalog.validate_settings(p['index'])
    r=p['release']
    if not isinstance(r,dict) or set(r)!={'mode','public_only','require_validation','block_warnings'} or r['mode'] not in {'all_errors','no_new_errors'} or any(type(r[k]) is not bool for k in ('public_only','require_validation','block_warnings')):
        raise SafeError('发布策略无效。')
    d=p['deletion']
    if not isinstance(d,dict) or set(d)!={'approval_ttl_seconds','require_validation'} or type(d['approval_ttl_seconds']) is not int or not 30<=d['approval_ttl_seconds']<=3600 or type(d['require_validation']) is not bool:
        raise SafeError('删除策略无效；必须保留本机逐计划批准。')
    return p


def load(store, root):
    record=metadata(store,root,'policy')
    return validate_policy(record['policy']) if record else copy.deepcopy(DEFAULT)


def user_import(store, root, data):
    """Local GUI callback: not registered as an MCP action."""
    p=validate_policy(data)
    with store.transaction():
        put(store,root,'policy',{'policy':p,'digest':digest(p),'imported_at':time.time()})
        store._bump()
    return {'policy_hash':digest(p),'name':p['name'],'baseline_invalidated':True}


def match(rule, name, path, kind='', visibility=''):
    return (fnmatch.fnmatchcase(name,rule.get('name','*')) and
            fnmatch.fnmatchcase(path,rule.get('path','*')) and
            ('kinds' not in rule or kind in rule['kinds']) and
            ('visibility' not in rule or visibility in rule['visibility']))


def severity(p, rule, entity, path):
    level=p['rules'][rule]
    for override in p['overrides']:
        if match(override,entity.name,path,entity.kind,entity.protection):
            level=override.get('rules',{}).get(rule,level)
    return level


def exemption(p, rule, entity, path):
    from datetime import date
    for e in p['exemptions']:
        if e['rule']==rule and match(e,entity.name,path):
            if e.get('expires') and date.fromisoformat(e['expires']) < date.today(): continue
            return e['reason']
    return ''


def user_accept_baseline(engine):
    """Capture the full-root report using trusted index settings, never MCP."""
    from .quality import audit
    p=load(engine.store,engine.root)
    check_index(engine,p)
    report=audit(engine,path='',public_only=p['release']['public_only'],limit=1,full_root=True)
    full=json.loads(Path(report['report']).read_text(encoding='utf-8'))
    baseline={'policy_hash':digest(p),'issues':full['issue_fingerprints'],
              'source_snapshot':full['source_snapshot'],'created_at':time.time(),
              'report':report['report']}
    with engine.store.transaction():
        put(engine.store,engine.root,'baseline',baseline)
    return {'status':'baseline_accepted','issues':len(baseline['issues']),'policy_hash':digest(p)}


def check_index(engine,p):
    engine.catalog.load_settings()
    actual={k:engine.catalog.settings[k] for k in ('exclude','defines')}
    if actual != p['index']:
        raise SafeError('当前索引范围/宏与用户批准的发布规则不一致。不能改exclude/defines或scope绕过门禁；请在本地GUI复核并导入规则。')
