import json
import tempfile
import unittest
from pathlib import Path

from tools.check_localization import find_gaps, gather_entries, read_archives, unlocalized_literals_added


class LocalizationChecks(unittest.TestCase):
    def test_new_literal_text_requires_a_localization_identity(self):
        old = 'FText::FromString(TEXT("Existing"))'
        new = old + '\nFText::FromString(\nFString::Printf(TEXT("同类 · %d"), count))'
        self.assertEqual(unlocalized_literals_added(old, new), ['同类 · %d'])
        self.assertEqual(unlocalized_literals_added('', 'NSLOCTEXT("UI", "Count", "同类 · {0}")'), [])
        self.assertEqual(unlocalized_literals_added('', 'FText::FromString(TEXT("+"))'), [])

    def test_missing_empty_and_stale_translations(self):
        entry = dict(namespace="UI", key="Language", source="语言")
        self.assertEqual(find_gaps([entry], [dict(entry, zh="语言", en="Language")]), [])
        self.assertEqual(find_gaps([entry], [dict(entry, zh="语言", en=" ")])[0]["missing_languages"], ["en"])
        self.assertTrue(find_gaps([dict(entry, source="界面语言")], [dict(entry, zh="语言", en="Language")])[0]["source_changed"])
        self.assertEqual(find_gaps([entry], [dict(namespace="Other", key="Language", zh="语言", en="Language")])[0]["missing_languages"], ["zh", "en"])

    def test_native_manifest_and_empty_gather(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "Game.manifest"
            path.write_text(json.dumps(dict(Namespace="UI", Children=[dict(Source=dict(Text="语言"), Keys=[dict(Key="Language", Path="Settings.cpp")])])), encoding="utf-8")
            self.assertEqual(gather_entries(path), [dict(namespace="UI", key="Language", source="语言", location="Settings.cpp")])
            path.write_text(path.read_text(encoding="utf-8"), encoding="utf-16")
            self.assertEqual(gather_entries(path)[0]["key"], "Language")
            path.write_text("{}", encoding="utf-8")
            with self.assertRaises(ValueError):
                gather_entries(path)

    def test_conflicting_catalogs_do_not_silently_override(self):
        with self.assertRaises(ValueError):
            find_gaps([], [dict(namespace="UI", key="Language", zh="语言", en="Language"),
                           dict(namespace="UI", key="Language", zh="语言", en="Locale")])

    def test_native_archives_keep_source_hash_input(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = []
            for language, text in (("zh", "文字\r\n说明"), ("en", "Text\r\nDescription")):
                path = Path(folder) / (language + ".archive")
                path.write_text(json.dumps(dict(Namespace="UI", Children=[dict(
                    Key="Description", Source=dict(Text="文字\r\n说明"), Translation=dict(Text=text))])), encoding="utf-16")
                paths.append(language + "=" + str(path))
            rows = read_archives(paths)
            self.assertEqual(find_gaps([dict(namespace="UI", key="Description", source="文字\r\n说明")], rows), [])
            self.assertTrue(find_gaps([dict(namespace="UI", key="Description", source="文字\n说明")], rows)[0]["source_changed"])
            rows[0]['zh'] = '文字\n说明'
            self.assertTrue(find_gaps([dict(namespace="UI", key="Description", source="文字\r\n说明")], rows)[0]['native_newlines_changed'])

    def test_mcp_localization_check_uses_native_inputs(self):
        from maintenance.engine import Engine
        from maintenance.protocol import Server
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'Content/Localization/Game'
            target.mkdir(parents=True)
            manifest = dict(Namespace='UI', Children=[dict(Source=dict(Text='语言'), Keys=[dict(Key='Language')])])
            (target / 'Game.manifest').write_text(json.dumps(manifest), encoding='utf-16')
            for culture, text in [('zh-Hans-CN', '语言'), ('en', '')]:
                (target / culture).mkdir()
                (target / culture / 'Game.archive').write_text(json.dumps(dict(Namespace='UI', Children=[dict(
                    Key='Language', Source=dict(Text='语言'), Translation=dict(Text=text))])), encoding='utf-16')
            engine = Engine.__new__(Engine)
            engine.root = str(Path(folder).resolve())
            server = Server(engine)
            server.initialized = True
            response = server.process(dict(jsonrpc='2.0', id=1, method='tools/call', params=dict(
                name='Configure', arguments=dict(action='check_localization'))))
            result = response['result']['structuredContent']
            self.assertEqual(result['gathered'], 1)
            self.assertEqual(result['gaps'][0]['missing_languages'], ['en'])


if __name__ == "__main__":
    unittest.main()
