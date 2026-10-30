"""Installer preflight, compact previews and single-snapshot import regression."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from maintenance import records
from tools.install_skill import install
from maintenance.profile import Profile

class DeliveryTests(unittest.TestCase):
    def test_skill_idempotence_no_config_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'config.toml').write_text('preserve')
            first=install(p);again=install(p)
            self.assertGreater(first['installed_files'],0);self.assertEqual(again['installed_files'],0)
            self.assertEqual((p/'config.toml').read_text(),'preserve')
    def test_skill_conflict_refuses_before_any_write(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);target=p/'.agents/skills/ue-maintenance/references/OPERATIONS.md'
            target.parent.mkdir(parents=True);target.write_text('mine')
            with self.assertRaisesRegex(ValueError,'differs'):install(p)
            self.assertFalse((p/'.agents/skills/ue-maintenance/SKILL.md').exists());self.assertEqual(target.read_text(),'mine')
    def test_preview_large_field_bounded_not_plan(self):
        original=[{'key':'x','change':'edit','fields':{'Text':{'before':'o','after':'字'*100000}}}]
        shown,more=records.compact_changes(original)
        self.assertTrue(more);self.assertLess(len(json.dumps(shown,ensure_ascii=False)),2000)
        self.assertEqual(len(original[0]['fields']['Text']['after']),100000)
    def test_preview_many_fields_bounded(self):
        original=[{'key':str(i),'change':'add','fields':{str(k):{'before':None,'after':'V'*299} for k in range(1000)}} for i in range(20)]
        shown,more=records.compact_changes(original)
        self.assertTrue(more);self.assertLess(len(json.dumps(shown)),12000)
    def test_import_reads_one_byte_snapshot(self):
        b={'key':'Id','fields':{'Id':{'type':'string'}}}
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'input.json';p.write_text('[]')
            with patch('maintenance.records.read_bytes',return_value=b'[{"Id":"one"}]') as read:
                rows,_,guard=records.import_rows(d,'input.json',{'Id':'Id'},b)
                self.assertEqual(read.call_count,1);self.assertEqual(json.loads(guard),rows)
    def test_no_implicit_profile_authorization(self):
        with tempfile.TemporaryDirectory() as d:
            p=Profile(d)
            self.assertEqual(p.mode,'read_only')
            with self.assertRaises(Exception):p.authorize('code')
            with self.assertRaises(Exception):p.authorize('data')
