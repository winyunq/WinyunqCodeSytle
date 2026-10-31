"""Two website views over the existing Doxygen engine; API source stays unchanged."""
from __future__ import annotations
import html
import json
import re
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

from doxygenue.cpp import SafeError, sha
from doxygenue.doc_pipeline import run_doxygen
from doxygenue.doxygen import dump_atomic, quote, xml_text
from doxygenue.views import documentation_from_xml
from .common import path_in
from .website_translations import TranslationMemory, source_hash

ASSETS = Path(__file__).parent / 'web_assets'
UI = {
    'en': dict(start='Get started', reference='API reference', developer='Developer reference',
               search='Search this documentation', inputs='Inputs', outputs='Outputs',
               contents='On this page', overview='Overview', menu='Contents', skip='Skip to content',
               returns='Returns', notes='Notes', warnings='Warnings', native='C++ declaration',
               tparams='Template parameters', return_values='Return values', exceptions='Exceptions',
               preconditions='Preconditions', postconditions='Postconditions', see='See also', enum_values='Values',
               experimental='Experimental', example='Example', version='Version', internal='Implementation notes',
               user='User reference', intro='Browse the reference', heading='Documentation',
               subtitle='Explore the API, parameters, and examples.',
               no_description='No description provided.', empty='No matching declarations in this section.'),
    'zh-CN': dict(start='开始使用', reference='接口参考', developer='开发者参考',
                  search='搜索文档', inputs='输入', outputs='输出', returns='返回值', notes='说明',
                  contents='本页内容', overview='概述', menu='目录', skip='跳转到正文',
                  warnings='注意', native='C++ 声明', experimental='实验性', example='示例',
                  tparams='模板参数', return_values='返回值说明', exceptions='异常',
                  preconditions='前置条件', postconditions='后置条件', see='另请参阅', enum_values='枚举值',
                  version='版本', internal='实现说明', user='用户参考', intro='浏览参考文档', heading='项目文档',
                  subtitle='查看接口、参数与使用示例。',
                  no_description='尚未提供说明。', empty='本节暂时没有匹配的声明。')}


def _files(root, patterns):
    result = set()
    for pattern in patterns:
        if Path(pattern).is_absolute() or '..' in Path(pattern).parts:
            raise SafeError('网页输入使用项目内相对 glob。')
        for path in Path(root).glob(pattern):
            if path.is_file():
                path_in(root, str(path.relative_to(root)))
                result.add(path.resolve())
    return sorted(result)


def _language_blocks(node, language_sections):
    seeds = {}
    for section in node.findall('.//simplesect[@kind="par"]'):
        title = xml_text(section.find('title'))
        for language, pattern in language_sections.items():
            if re.fullmatch(pattern, title):
                seeds[language] = '\n'.join(xml_text(p) for p in section.findall('para')).strip()
    return seeds


def _records(folder, root, allowed, groups, options, *, public_only=True):
    found = {}
    sections = options.get('language_sections', {'zh-CN': '中文|Chinese|zh-CN'})
    split = options.get('bilingual_separator_regex', r'\s+/\s+(?=[\u3400-\u9fff])')
    for index in ET.parse(folder / 'index.xml').getroot().findall('compound'):
        compound = ET.parse(folder / (index.get('refid') + '.xml')).getroot().find('compounddef')
        if compound is None:
            continue
        owner = compound.findtext('compoundname', '')
        nodes = compound.findall('.//memberdef')
        if compound.get('kind') in {'class', 'struct', 'namespace'}:
            nodes.insert(0, compound)
        for member in nodes:
            if (public_only and member.get('prot', 'public') != 'public') or member.get('kind') not in {'function', 'variable', 'enum', 'typedef', 'class', 'struct', 'namespace'}:
                continue
            location = member.find('location')
            if location is None or not location.get('file'):
                continue
            file = Path(location.get('file'))
            if not file.is_absolute():
                file = Path(root) / file
            file = file.resolve()
            if file not in allowed:
                continue
            leaf = member.findtext('name', '') if member is not compound else owner.rsplit('::', 1)[-1]
            name = owner if member is compound else member.findtext('qualifiedname') or (owner + '::' + leaf if compound.get('kind') in {'class', 'struct', 'namespace'} else leaf)
            group = next((g for g in groups if any(file in selected and re.search(pattern, name)
                                                   for selected, pattern in g['_selectors'])), None)
            if group is None:
                continue
            signature = (member.findtext('definition', name) + member.findtext('argsstring', '')).strip()
            key = source_hash(name + '\n' + signature)[:24]
            if key in found:
                continue
            doc_node = ET.Element('documentation')
            for tag in ('briefdescription', 'detaileddescription', 'inbodydescription'):
                doc_node.extend(member.findall(tag))
            doc = documentation_from_xml(doc_node)
            brief = doc.get('brief', '')
            parts = re.split(split, brief, maxsplit=1)
            seeds = _language_blocks(doc_node, sections)
            if len(parts) == 2:
                brief = parts[0]
                seeds.setdefault('zh-CN', parts[1])
            for paragraph in member.findall('detaileddescription/para'):
                bilingual = re.split(split, ' ' + xml_text(paragraph), maxsplit=1)
                if len(bilingual) == 2 and not bilingual[0].strip():
                    seeds.setdefault('zh-CN', bilingual[1].strip())
            full = doc.get('full', {})
            parameters = []
            for param in member.findall('param'):
                label = param.findtext('declname') or param.findtext('defname')
                if label and (not public_only or label not in options.get('hidden_parameters', [])):
                    desc = doc.get('params', {}).get(label, '')
                    if isinstance(desc, dict):
                        desc = desc.get('description', '')
                    parameters.append(dict(name=label, type=xml_text(param.find('type')),
                                           default=xml_text(param.find('defval')), description=desc))
            # Language paragraphs are projected separately; they are not repeated in every language.
            detail = full.get('details', '')
            found[key] = dict(id=key, name=name, leaf=leaf, kind=member.get('kind'),
                              signature=signature, group=group['id'],
                              file=file.relative_to(root).as_posix(), line=int(location.get('line', 0)),
                              brief=brief, details=detail, params=parameters,
                              returns=full.get('returns', doc.get('returns', '')),
                              notes=full.get('notes', []), warnings=full.get('warnings', []),
                              internal=full.get('internal', []) if not public_only else [], seeds=seeds,
                              sections={key: full.get(key, {}) for key in ('tparams', 'return_values', 'exceptions', 'preconditions', 'postconditions', 'see')})
            found[key]['sections']['enum_values'] = {value.findtext('name', ''): [
                {'code': value.findtext('name', '') + ' ' + xml_text(value.find('initializer'))},
                documentation_from_xml(value).get('brief', ''),
                documentation_from_xml(value).get('full', {}).get('details', [])]
                for value in member.findall('enumvalue')}
    return sorted(found.values(), key=lambda r: (r['group'], r['name'], r['signature']))


def _rich(value, translate, field):
    if not value:
        return ''
    if isinstance(value, str):
        return '<p>' + html.escape(translate(field, value)) + '</p>'
    if isinstance(value, list):
        return ''.join(_rich(v, translate, field + '/' + str(i)) for i, v in enumerate(value))
    if isinstance(value, dict):
        if 'code' in value:
            return '<pre><code>' + html.escape(value['code']) + '</code></pre>'
        if 'items' in value or 'steps' in value:
            tag, items = ('ol', value['steps']) if 'steps' in value else ('ul', value['items'])
            return '<' + tag + '>' + ''.join('<li>' + _rich(v, translate, field + '/' + str(i)) + '</li>' for i, v in enumerate(items)) + '</' + tag + '>'
        if 'table' in value:
            return '<table>' + ''.join('<tr>' + ''.join('<td>' + _rich(cell, translate, field + f'/{i}/{j}') + '</td>' for j, cell in enumerate(row)) + '</tr>' for i, row in enumerate(value['table'])) + '</table>'
        if 'description' in value:
            return _rich(value['description'], translate, field)
        if 'title' not in value and 'content' not in value:
            return '<dl>' + ''.join('<dt><code>' + html.escape(key) + '</code></dt><dd>' + _rich(item, translate, field + '/' + key) + '</dd>' for key, item in value.items()) + '</dl>'
        title = value.get('title', '')
        if title in {'中文', 'Chinese', 'zh-CN', 'English', '英文'}:
            return ''
        return ('<h4>' + html.escape(translate(field + '/title', title)) + '</h4>' if title else '') + _rich(value.get('content', ''), translate, field + '/content')
    return ''


def _localized_record(record, language, memory, localization, group, options, words, audience):
    def translate(field, text, seed=''):
        bilingual = re.split(options.get('bilingual_separator_regex', r'\s+/\s+(?=[\u3400-\u9fff])'), ' ' + text, maxsplit=1)
        if len(bilingual) == 2:
            text = bilingual[0].strip()
            if language == 'zh-CN':
                seed = bilingual[1].strip()
        if memory is None:
            return text
        return memory.text(record['id'] + ':' + field, text,
                           metadata=dict(file=record['file'], name=record['name'], field=field), seed=seed)
    cls, _, leaf = record['name'].rpartition('::')
    lookup = localization.get('functions', {}).get(cls.removeprefix('U') + '.' + leaf, {})
    terms = localization.get('terms', {})
    def term(value):
        return translate('term/' + value, value, terms.get(value, ''))
    title = group.get('display_names', {}).get(record['leaf'], record['leaf'])
    title = translate('title/' + audience, title, lookup.get('name', ''))
    seed = record['seeds'].get(language) or lookup.get('tip', '')
    brief = translate('brief', record['brief'], seed) if record['brief'] else ''
    params = ''.join('<tr><th>' + html.escape(term(p['name'])) + '<code>' + html.escape(p['name']) + '</code></th><td><span class="type">' + html.escape(p['type']) + '</span>' +
                     ('<code class="default">' + html.escape(p['default']) + '</code>' if p['default'] else '') +
                     ('<p>' + html.escape(translate('param/' + p['name'], p['description'])) + '</p>' if p['description'] else '') + '</td></tr>' for p in record['params'])
    async_node = bool(re.search(group.get('async_regex', '(?!)'), record['name']))
    outputs = ''.join('<span><b>' + html.escape(term(event)) + '</b><code>' + html.escape(payload) + '</code></span>' for event, payload in group.get('async_outputs', {}).items()) if async_node else ''
    parts = ['<article class="api-card" id="' + record['id'] + '"><div class="api-heading"><span class="kind">' + html.escape(record['kind']) + '</span><h2>' + html.escape(title) + '</h2></div>',
             '<code class="api-name">' + html.escape(record['name']) + '</code>', '<p class="brief">' + html.escape(brief) + '</p>',
             _rich(record['details'], translate, 'details')]
    if params:
        parts += ['<h3>' + words['inputs'] + '</h3><table class="parameters">' + params + '</table>']
    if outputs:
        parts += ['<h3>' + words['outputs'] + '</h3><div class="outputs">' + outputs + '</div>']
    if record['returns'] and not async_node:
        parts += ['<h3>' + words['returns'] + '</h3>', _rich(record['returns'], translate, 'returns')]
    for field, value in record['sections'].items():
        if value:
            parts += ['<h3>' + words[field] + '</h3>', _rich(value, translate, field)]
    for field in ('notes', 'warnings', 'internal'):
        if record[field]:
            parts += ['<aside class="' + field + '"><h3>' + words[field] + '</h3>', _rich(record[field], translate, field), '</aside>']
    parts += ['<details><summary>' + words['native'] + '</summary><pre><code>' + html.escape(record['signature']) + '</code></pre><small>' + html.escape(record['file']) + ':' + str(record['line']) + '</small></details></article>']
    return dict(html=''.join(parts), id=record['id'], title=title, name=record['name'], group=record['group'], brief=brief)


def _label(group, field, language, source_language):
    value = group.get(field, '')
    return value.get(language, value.get(source_language, '')) if isinstance(value, dict) else value


def _page(config, groups, language, languages, current, content, search, version, audience, audiences):
    words = UI.get(language, UI['en'])
    source_language = config.get('source_language', 'en')
    def label(g):
        return _label(g, 'title', language, source_language) or g['id']
    nav = '<a class="nav-home' + (' active' if current == 'index' else '') + '" href="index.html">' + words['start'] + '</a><div class="nav-caption">' + words['reference'] + '</div>'
    entries = [row for row in search if row['group'] == current]
    for group in groups:
        selected = current == group['id']
        link = '<a class="nav-item' + (' active' if selected else '') + '" href="' + group['id'] + '.html"><span>' + html.escape(label(group)) + '</span>' + ('<i>β</i>' if group.get('experimental') else '') + '</a>'
        if selected and entries:
            children = ''.join('<li><a href="#' + row['id'] + '">' + html.escape(row['title']) + '</a></li>' for row in entries)
            nav += '<details class="nav-group" open><summary>' + link + '</summary><ul class="nav-symbols">' + children + '</ul></details>'
        else:
            nav += link
    audience_links = ''.join('<a' + (' aria-current="page"' if view == audience else '') + ' href="../../' + view + '/' + language + '/index.html">' + words[view] + '</a>' for view in audiences)
    language_links = ''.join('<a' + (' aria-current="page"' if code == language else '') + ' href="../' + code + '/' + current + '.html">' + html.escape({'en':'English','zh-CN':'简体中文'}.get(code, code)) + '</a>' for code in languages)
    data = json.dumps(search, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    title = config.get('title', 'API Documentation')
    current_group = next((g for g in groups if g['id'] == current), None)
    page_title = label(current_group) if current_group else words['start']
    toc = '<a href="#overview">' + words['overview'] + '</a>'
    if current == 'index':
        toc += '<a href="#reference">' + words['reference'] + '</a>'
    elif _label(current_group, 'example', language, source_language):
        toc += '<a href="#example">' + words['example'] + '</a>'
    toc += ''.join('<a href="#' + row['id'] + '">' + html.escape(row['title']) + '</a>' for row in entries)
    asset_version = sha((ASSETS / 'site.css').read_bytes() + (ASSETS / 'site.js').read_bytes())[:12]
    return f'''<!doctype html><html lang="{language}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)} · {html.escape(page_title)}</title><link rel="stylesheet" href="../../assets/site.css?v={asset_version}"><script defer src="../../assets/site.js?v={asset_version}"></script></head><body>
<a class="skip-link" href="#main-content">{words['skip']}</a>
<header><button class="menu-toggle" aria-controls="project-navigation" aria-expanded="false">☰ {words['menu']}</button><a class="brand" href="index.html"><span class="brand-mark">{html.escape(title[:1])}</span>{html.escape(title)}</a><nav class="header-nav">{audience_links}</nav><div class="header-search"><label class="search"><span aria-hidden="true">⌕</span><input id="search" type="search" placeholder="{words['search']}" aria-label="{words['search']}"></label><div id="search-results" hidden></div></div><nav class="languages">{language_links}</nav></header>
<aside class="sidebar" id="project-navigation"><div class="sidebar-title">{html.escape(title)}</div><div class="version"><span>{words['version']}</span><strong>{html.escape(version)}</strong></div><nav aria-label="{words['menu']}">{nav}</nav><footer>{words[audience]}</footer></aside>
<main id="main-content" tabindex="-1"><nav class="breadcrumbs" aria-label="{words['heading']}"><a href="index.html">{html.escape(title)}</a><span>/</span><span>{words[audience]}</span><span>/</span><span>{html.escape(page_title)}</span></nav>{content}</main>
<aside class="page-toc"><nav aria-label="{words['contents']}"><h2>{words['contents']}</h2>{toc}</nav></aside><script type="application/json" id="search-index">{data}</script></body></html>'''


def _groups(root, config, audience):
    if audience == 'user':
        groups = [dict(g) for g in config.get('groups', [])]
        patterns = config.get('user_inputs', ['Source/**/*.h', 'Source/**/*.hpp'])
    else:
        groups = [dict(g) for g in config.get('developer_groups', [])]
        patterns = config.get('developer_inputs', ['Source/**/*.cpp', 'Source/**/*.h', 'Source/**/*.hpp'])
    if not groups:
        groups = [dict(id='Reference', title=dict(en='API reference', **{'zh-CN': '接口参考'}), headers=patterns)]
    ids = [g.get('id', '') for g in groups]
    if len(ids) != len(set(ids)) or any(not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*', value) for value in ids):
        raise SafeError('文档分组 id 应为不重复的字母、数字、下划线或连字符。')
    for group in groups:
        group['_selectors'] = []
        for entry in group.get('headers', []):
            pattern = entry if isinstance(entry, str) else entry['glob']
            symbols = group.get('symbols_regex', '.*') if isinstance(entry, str) else entry.get('symbols_regex', group.get('symbols_regex', '.*'))
            try:
                re.compile(symbols)
            except re.error as error:
                raise SafeError('文档分组正则错误：' + str(error)) from error
            group['_selectors'].append((set(_files(root, [pattern])), symbols))
        group['_files'] = set().union(*(selected for selected, _ in group['_selectors'])) if group['_selectors'] else set()
        if audience == 'user' and any(p.suffix.lower() not in {'.h', '.hpp', '.hh', '.hxx'} for p in group['_files']):
            raise SafeError('用户文档只接受头文件。')
    return groups


def _render(config, groups, records, output, languages, memories, localization, version, audience, audiences):
    source_language = config.get('source_language', 'en')
    overview = config.get('overview', {})
    for language in languages:
        memory = memories.get(language)
        loc = localization if language == config.get('localization_language', 'zh-CN') else {}
        words = UI.get(language, UI['en'])
        rendered = [_localized_record(r, language, memory, loc, next(g for g in groups if g['id'] == r['group']), config, words, audience) for r in records]
        search = [{key: r[key] for key in ('id', 'title', 'name', 'group', 'brief')} for r in rendered]
        pages = output / audience / language
        pages.mkdir(parents=True, exist_ok=True)
        cards = ''.join('<a class="family-card" href="' + g['id'] + '.html"><h2>' + html.escape(_label(g, 'title', language, source_language) or g['id']) + '</h2><p>' + html.escape(_label(g, 'description', language, source_language)) + '</p><span class="card-link">' + words['reference'] + ' →</span></a>' for g in groups)
        heading = _label(overview, 'heading', language, source_language) or config.get('title', words['heading'])
        subtitle = _label(overview, 'description', language, source_language) or words['subtitle']
        content = '<section class="hero" id="overview"><span class="eyebrow">' + words[audience] + '</span><h1>' + html.escape(heading) + '</h1><p>' + html.escape(subtitle) + '</p></section><h2 class="section-heading" id="reference">' + words['intro'] + '</h2><div class="family-grid">' + cards + '</div>'
        (pages / 'index.html').write_text(_page(config, groups, language, languages, 'index', content, search, version, audience, audiences), encoding='utf-8')
        for group in groups:
            title = _label(group, 'title', language, source_language) or group['id']
            content = '<section class="page-heading" id="overview"><span class="eyebrow">' + group['id'] + '</span><h1>' + html.escape(title) + '</h1><p>' + html.escape(_label(group, 'description', language, source_language)) + '</p>' + ('<span class="experimental">' + words['experimental'] + '</span>' if group.get('experimental') else '') + '</section>'
            example = _label(group, 'example', language, source_language)
            if example:
                content += '<section class="quick-start" id="example"><h2>' + words['example'] + '</h2><pre><code>' + html.escape(example) + '</code></pre></section>'
            content += ''.join(r['html'] for r in rendered if r['group'] == group['id']) or '<p>' + words['empty'] + '</p>'
            (pages / (group['id'] + '.html')).write_text(_page(config, groups, language, languages, group['id'], content, search, version, audience, audiences), encoding='utf-8')


def generate_website(engine, *, audience='both', languages=None):
    engine.profile.assert_current()
    config = engine.profile.data.get('documentation')
    if not isinstance(config, dict):
        raise SafeError('项目 profile 尚未配置 documentation。')
    if audience not in {'user', 'developer', 'both'}:
        raise SafeError('audience 为 user/developer/both。')
    languages = languages or config.get('languages', ['en', 'zh-CN'])
    if not languages or any(not re.fullmatch(r'[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*', language) for language in languages):
        raise SafeError('languages 使用 en、zh-CN 等语言代码。')
    root = Path(engine.root)
    output = path_in(engine.root, config.get('output', 'Saved/Documentation/Website'), must_exist=False)
    output.mkdir(parents=True, exist_ok=True)
    version = config.get('version', '')
    if config.get('version_file'):
        descriptor = json.loads(path_in(engine.root, config['version_file']).read_text('utf-8-sig'))
        version = str(descriptor.get('VersionName', version))
    result = dict(status='generated', audience=audience, output=str(output), index=str(output/'index.html'),
                  version=version, source_only=True, publication='local')
    predefined = 'PREDEFINED += ' + ' '.join(quote(value) for value in config.get('defines', [])) + '\n'
    assets = output / 'assets'
    assets.mkdir(exist_ok=True)
    for name in ('site.css', 'site.js'):
        shutil.copyfile(ASSETS/name, assets/name)
    source_language = config.get('source_language', 'en')
    memory_dir = path_in(engine.root, config.get('translation_directory', 'Documentation/Translations'), must_exist=False)
    memories = {language: TranslationMemory(memory_dir / (language + '.json'), language) for language in languages if language != source_language}
    localization = {}
    if config.get('localization_seed'):
        localization = json.loads(path_in(engine.root, config['localization_seed']).read_text('utf-8-sig'))
    audiences = ['user', 'developer'] if audience == 'both' else [audience]
    all_files = set()
    for view in audiences:
        groups = _groups(root, config, view)
        files = sorted(set().union(*(g['_files'] for g in groups)))
        if not files:
            raise SafeError('文档输入没有匹配的文件：' + view)
        all_files.update(files)
        destination = output / (view + '-source')
        destination.mkdir(exist_ok=True)
        extra = predefined + 'INTERNAL_DOCS = ' + ('NO' if view == 'user' else 'YES') + '\n'
        run_doxygen(engine.code, files, destination, public_only=view == 'user', extra_config=extra)
        records = _records(destination / 'xml', root, set(files), groups, config, public_only=view == 'user')
        _render(config, groups, records, output, languages, memories, localization, version, view, audiences)
        result[view + '_files'] = [p.relative_to(root).as_posix() for p in files]
        result[view + '_declarations'] = len(records)
        if view == 'user':
            result.update(declarations=len(records), groups={g['id']: sum(r['group'] == g['id'] for r in records) for g in groups})
    reports = [memory.save() for memory in memories.values()]
    dump_atomic(memory_dir / 'state.json', dict(version=1, source_language=source_language,
                files=[dict(file=p.relative_to(root).as_posix(), sha256=sha(p.read_bytes())) for p in sorted(all_files)], translations=reports))
    result.update(languages=languages, translations=reports, translation_state=str(memory_dir / 'state.json'))
    target = audiences[0] + '/' + languages[0] + '/index.html'
    (output/'index.html').write_text('<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="refresh" content="0;url='+target+'"><title>'+html.escape(config.get('title','Documentation'))+'</title></head><body><a href="'+target+'">Open documentation</a></body></html>',encoding='utf-8')
    dump_atomic(output/'manifest.json',result)
    return result
