import json
from pathlib import Path
import shutil
import tempfile
import unittest

from doxygenue.store import Store
from maintenance.engine import Engine
from maintenance.protocol import Server


@unittest.skipUnless(shutil.which('doxygen'), 'real Doxygen required')
class WebsiteWorkflow(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'Project'
        (self.root / 'Source').mkdir(parents=True)
        self.header = self.root / 'Source/Chat.h'
        self.header.write_text('''class Chat {
public:
    /** @brief Talk to one AI.
     * @param Message Your message.
     * @return The reply.
     * @retval nullptr NoReplyAvailable.
     * @pre RequiresInitializedSession.
     * @code
     * Chat::ChatOne("hello");
     * @endcode
     * @par 中文
     * 和一个 AI 对话。
     */
    static const char* ChatOne(const char* Message);
    /** @brief Talk to a named AI. / 和具名 AI 对话。 */
    static const char* ChatMulti(const char* Name, const char* Message);
private:
    /** @brief PrivateSecretMustNotLeak. */
    void Secret();
};
''', encoding='utf-8')
        (self.root / 'Source/Chat.cpp').write_text('''#include "Chat.h"
/** @brief DeveloperImplementationOnly. */
static int InternalCompute() { return 1; }
const char* Chat::ChatOne(const char* Message) { return Message; }
const char* Chat::ChatMulti(const char* Name, const char* Message) { return Message; }
''', encoding='utf-8')
        groups = []
        for name in ('Basics', 'Batch'):
            groups.append(dict(id=name, title=dict(en=name, **{'zh-CN': name}),
                               description=dict(en='API guide', **{'zh-CN': '接口指南'}),
                               headers=[dict(glob='Source/Chat.h', symbols_regex='::ChatOne$' if name == 'Basics' else '::ChatMulti$')]))
        fields = {key: dict(type='string') for key in ('id', 'file', 'name', 'field', 'source_text', 'source_hash', 'translation', 'translated_source_hash')}
        fields['reviewed'] = dict(type='boolean')
        (self.root / 'Docs/Translations').mkdir(parents=True)
        (self.root / 'Docs/Translations/zh-CN.json').write_text('[]', encoding='utf-8')
        self.profile = self.root / 'profile.json'
        self.profile.write_text(json.dumps(dict(version=1, mode='maintain',
            data=[dict(name='Translations', path='Docs/Translations/zh-CN.json', key='id', fields=fields)],
            documentation=dict(title='Fixture Docs', version='1.0', output='Saved/Website',
                               source_language='en', languages=['en', 'zh-CN'],
                               translation_directory='Docs/Translations', groups=groups))), encoding='utf-8')
        self.store = Store(Path(self.temp.name) / 'state.sqlite3')
        self.addCleanup(self.store.close)
        self.server = Server(Engine(str(self.root), self.store, str(self.profile), shutil.which('doxygen')))
        self.server.process(dict(jsonrpc='2.0', id=0, method='initialize', params={}))
        self.next_id = 1

    def call(self, tool, **arguments):
        self.next_id += 1
        response = self.server.process(dict(jsonrpc='2.0', id=self.next_id, method='tools/call',
                                            params=dict(name=tool, arguments=arguments)))
        self.assertNotIn('error', response)
        result = response['result']
        self.assertFalse(result.get('isError'), result.get('content'))
        return result['structuredContent']

    def test_two_audiences_and_header_groups(self):
        result = self.call('Configure', action='generate_website')
        self.assertEqual(result['declarations'], 2)
        self.assertTrue(all(path.endswith('.h') for path in result['user_files']))
        self.assertIn('Source/Chat.cpp', result['developer_files'])
        folder = self.root / 'Saved/Website'
        user = (folder / 'user/en/Basics.html').read_text('utf-8')
        self.assertIn('Talk to one AI.', user)
        self.assertIn('NoReplyAvailable.', user)
        self.assertIn('RequiresInitializedSession.', user)
        self.assertIn('<pre><code>Chat::ChatOne', user)
        self.assertNotIn('ChatMulti', user.split('<script type="application/json"')[0])
        self.assertNotIn('PrivateSecretMustNotLeak', user)
        self.assertNotIn('DeveloperImplementationOnly', user)
        chinese = (folder / 'user/zh-CN/Basics.html').read_text('utf-8')
        self.assertIn('和一个 AI 对话。', chinese)
        batch_en = (folder / 'user/en/Batch.html').read_text('utf-8')
        batch_zh = (folder / 'user/zh-CN/Batch.html').read_text('utf-8')
        self.assertNotIn('和具名 AI 对话', batch_en)
        self.assertIn('和具名 AI 对话。', batch_zh)
        developer = (folder / 'developer/en/Reference.html').read_text('utf-8')
        self.assertIn('DeveloperImplementationOnly', developer)
        self.assertIn('PrivateSecretMustNotLeak', developer)
        self.assertEqual(developer.count('NoReplyAvailable.'), 1)
        self.assertIn('../../assets/site.css', developer)
        self.assertNotIn('AI', (folder / 'user/en/index.html').read_text('utf-8').split('<script type="application/json"')[0])
        self.assertEqual(set(result['groups']), {'Basics', 'Batch'})
        for group in result['groups']:
            self.assertTrue((folder / 'user/en' / (group + '.html')).is_file())

    def test_translation_data_tools_cache_hits_and_source_change(self):
        self.call('Configure', action='generate_website', audience='user')
        rows = self.call('Read', name='Translations', view='rows', limit=100)['rows']
        entry = next(row for row in rows if row['field'] == 'param/Message')
        plan = self.call('Write', name='Translations', rows=[dict(id=entry['id'],
            translation='你的消息。<script>alert(1)</script>', translated_source_hash=entry['source_hash'], reviewed=True)])
        self.call('Write', action='apply', plan=plan['plan'])
        second = self.call('Configure', action='generate_website', audience='user')
        self.assertGreater(second['translations'][0]['hits'], 0)
        page = self.root / 'Saved/Website/user/zh-CN/Basics.html'
        self.assertIn('你的消息。&lt;script&gt;', page.read_text('utf-8'))
        self.assertNotIn('<script>alert(1)</script>', page.read_text('utf-8'))
        self.header.write_text(self.header.read_text('utf-8').replace('Your message.', 'Your next message.'), encoding='utf-8')
        third = self.call('Configure', action='generate_website', audience='user')
        self.assertGreater(third['translations'][0]['stale'], 0)
        self.assertIn('Your next message.', page.read_text('utf-8'))
        old = self.call('Read', name='Translations', view='rows', where=dict(id=entry['id']))['rows'][0]
        self.assertIn('你的消息。', old['translation'])
        self.assertNotEqual(old['source_hash'], old['translated_source_hash'])
        self.header.write_text('\n\n' + self.header.read_text('utf-8'), encoding='utf-8')
        fourth = self.call('Configure', action='generate_website', audience='user')
        self.assertEqual(fourth['translations'][0]['missing'], third['translations'][0]['missing'])
        self.assertEqual(fourth['translations'][0]['stale'], third['translations'][0]['stale'])


if __name__ == '__main__':
    unittest.main()
