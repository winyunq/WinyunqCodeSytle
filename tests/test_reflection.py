"""Real parser and stdio regression tests for Unreal member annotations."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from doxygenue.cpp import Source
from maintenance.client import Client


class ReflectionRanges(unittest.TestCase):
    def test_template_members_use_cpp_grammar(self):
        for declaration, name in [
            ('TMap<FName, int32> CompletedLevelIndices;', 'CompletedLevelIndices'),
            ('TMap<FName, TArray<TPair<int32, FString>>> 科技索引;', '科技索引'),
            ('const Namespace::Value* Value = nullptr;', 'Value'),
        ]:
            with self.subTest(declaration=declaration):
                source = Source.load('Member.h', declaration.encode('utf-8'))
                self.assertEqual([(o.name, o.kind) for o in source.occurrences], [(name, 'variable')])

    def test_annotation_belongs_to_member_not_generated_body(self):
        declaration = 'UFUNCTION(BlueprintPure, Category="Settings", meta=(DisplayName="Mode"))\nint GetMode() const;'
        text = 'UCLASS() class USettings { GENERATED_BODY() public:\n' + declaration + '\nvoid Other(); };'
        source = Source.load('Settings.h', text.encode())
        self.assertEqual([o.name for o in source.occurrences], ['USettings::GetMode', 'USettings::Other'])
        occurrence = source.occurrences[0]
        self.assertEqual(source.text[occurrence.start:occurrence.end], declaration)

    def test_property_annotation_and_leading_comment(self):
        declaration = 'UPROPERTY(Config)\nint Value = 0;'
        source = Source.load('Settings.h', ('class USettings {\n// value\n' + declaration + '\n};').encode())
        occurrence = source.occurrences[0]
        self.assertEqual(source.text[occurrence.start:occurrence.end], declaration)
        self.assertEqual([c.value for c in source.leading(occurrence)], ['// value'])


class ReflectionWorkflow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        module = self.root / 'Source/Test'
        module.mkdir(parents=True)
        self.header = module / 'Settings.h'
        self.cpp = module / 'Settings.cpp'
        self.header.write_text('UCLASS()\nclass USettings {\nGENERATED_BODY()\npublic:\nint GetMode() const;\nvoid Other();\n};\n')
        self.cpp.write_text('#include "Settings.h"\nint USettings::GetMode() const { return 0; }\nvoid USettings::Other() {}\n')
        profile = self.root / 'profile.json'
        profile.write_text(json.dumps({'version': 1, 'mode': 'maintain', 'code_paths': ['Source/**/*.h', 'Source/**/*.cpp']}))
        self.client = Client(self.root, state_db=self.root / 'state/state.db', profile=profile)

    def tearDown(self):
        self.client.close()
        self.tmp.cleanup()

    def function(self, code):
        return self.client.call('Write', kind='function', path='Source/Test/Settings.cpp', new_code=code)

    def apply(self, preview):
        return self.client.call('Write', action='apply', plan=preview['plan'])

    def test_existing_modify_member_accepts_function_annotation(self):
        declaration = 'UFUNCTION(BlueprintPure, Category="Settings")\nint GetMode() const;'
        preview = self.client.call('Write', kind='code', operation='modify_member', name='USettings::GetMode',
            path='Source/Test/Settings.h', old_code='int GetMode() const;', new_code=declaration)
        self.apply(preview)
        self.assertIn(declaration, self.header.read_text())
        self.assertNotIn('UFUNCTION', self.cpp.read_text())

    def test_add_member_in_nested_struct_keeps_owner_and_other_fields(self):
        self.header.write_text('UCLASS()\nclass USettings {\nGENERATED_BODY()\npublic:\n'
                               'struct FRequest {\nint Entity;\nint Type;\n};\n'
                               'void Other();\n};\n')
        preview = self.client.call('Write', kind='code', operation='add_member',
                                   name='USettings::FRequest::Type', path='Source/Test/Settings.h',
                                   new_code='int AttachToAgentUID = -1;')
        self.apply(preview)
        source = Source.load(str(self.header))
        added = [o for o in source.occurrences if o.name == 'USettings::FRequest::AttachToAgentUID']
        self.assertEqual(len(added), 1)
        self.assertIn('int Entity;\nint Type;\nint AttachToAgentUID = -1;\n};', self.header.read_text())
        self.assertIn('void Other();', self.header.read_text())

    def test_add_member_requires_exact_nested_owner(self):
        self.header.write_text('class USettings { public: struct FRequest { int Type; }; };\n')
        before = self.header.read_bytes()
        with self.assertRaisesRegex(RuntimeError, '名称未找到或不唯一'):
            self.client.call('Write', kind='code', operation='add_member',
                             name='USettings::Type', path='Source/Test/Settings.h', new_code='int UID = -1;')
        self.assertEqual(self.header.read_bytes(), before)

    def test_add_template_member_through_real_mcp(self):
        self.header.write_text('class USettings { public: int Value; void Other(); };\n')
        preview = self.client.call('Write', kind='code', operation='add_member',
                                   name='USettings::Value', path='Source/Test/Settings.h',
                                   new_code='TMap<FName, int32> CompletedLevelIndices;')
        self.apply(preview)
        self.assertIn('TMap<FName, int32> CompletedLevelIndices;', self.header.read_text())
        self.assertIn('void Other();', self.header.read_text())
        before = self.header.read_bytes()
        for declaration in ['void Injected();', 'struct Nested { int X; };',
                            '#include "injected.h"\nint X;', 'int X; // hidden',
                            'TMap<FName,> Invalid;', 'int X, Y;']:
            with self.subTest(declaration=declaration), self.assertRaises(RuntimeError):
                self.client.call('Write', kind='code', operation='add_member',
                                 name='USettings::Value', path='Source/Test/Settings.h',
                                 new_code=declaration)
            self.assertEqual(self.header.read_bytes(), before)


    def test_function_payload_routes_annotation_to_header_and_preserves_on_edit(self):
        annotation = 'UFUNCTION(BlueprintPure, Category="Settings", meta=(DisplayName="Mode"))'
        self.apply(self.function(annotation + '\nint USettings::GetMode() const { return 1; }'))
        self.assertIn(annotation, self.header.read_text())
        self.assertNotIn('UFUNCTION', self.cpp.read_text())
        self.apply(self.function('int USettings::GetMode() const { return 2; }'))
        self.assertEqual(self.header.read_text().count(annotation), 1)
        self.assertIn('return 2;', self.cpp.read_text())
        self.assertIn('void Other();', self.header.read_text())

    def test_new_function_routes_annotation_to_header(self):
        self.apply(self.function('UFUNCTION(BlueprintCallable)\nvoid USettings::SetMode(int Value) { Other(); }'))
        self.assertIn('UFUNCTION(BlueprintCallable)\n', self.header.read_text())
        self.assertIn('void SetMode(int Value);', self.header.read_text())
        self.assertIn('    UFUNCTION(BlueprintCallable)\n    void SetMode(int Value);', self.header.read_text())
        self.assertNotIn('UFUNCTION', self.cpp.read_text())

    def test_extra_code_duplicate_annotations_and_changed_signature_rejected(self):
        before = self.header.read_bytes(), self.cpp.read_bytes()
        for code in ['UFUNCTION(BlueprintPure)\nint USettings::GetMode() const { return 1; }\nint Extra;',
                     'UFUNCTION(BlueprintPure)\nUFUNCTION(BlueprintCallable)\nint USettings::GetMode() const { return 1; }']:
            with self.subTest(code=code), self.assertRaises(RuntimeError):
                self.function(code)
        with self.assertRaises(RuntimeError):
            self.client.call('Write', kind='code', operation='modify_member', name='USettings::GetMode',
                path='Source/Test/Settings.h', old_code='int GetMode() const;',
                new_code='UFUNCTION(BlueprintPure)\nfloat GetMode() const;')
        self.assertEqual((self.header.read_bytes(), self.cpp.read_bytes()), before)

    def test_stale_header_still_rejects_apply(self):
        preview = self.function('UFUNCTION(BlueprintPure)\nint USettings::GetMode() const { return 1; }')
        self.header.write_text(self.header.read_text() + '\n// external edit\n')
        with self.assertRaisesRegex(RuntimeError, '变化|改变'):
            self.apply(preview)
        self.assertNotIn('UFUNCTION', self.header.read_text())


if __name__ == '__main__':
    unittest.main(verbosity=2)
