import os
import sys
import tempfile
import unittest


SCRIPT_DIRECTORY = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "scripts")
)
if SCRIPT_DIRECTORY not in sys.path:
    sys.path.insert(0, SCRIPT_DIRECTORY)

from WinyunqCodeSlicer import WinyunqCodeSlicer
from WinyunqTargetEditor import WinyunqTargetEditor


class TestWinyunqTargetEditor(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = self.temporary_directory.name
        self.header_path = os.path.join(self.root, "ExampleActor.h")
        self.source_path = os.path.join(self.root, "ExampleActor.cpp")
        with open(self.header_path, "w", encoding="utf-8") as stream:
            stream.write(
                """class AExampleActor
{
public:
    void UpdateInstances(int Count);
};
"""
            )
        with open(self.source_path, "w", encoding="utf-8") as stream:
            stream.write(
                """#include \"ExampleActor.h\"

void AExampleActor::UpdateInstances(int Count)
{
    /// Keep this statement explanation.
    CachedCount = Count;

    /// Keep the notification explanation.
    NotifyChanged();
}

void AExampleActor::UnrelatedFunction()
{
    DoNotTouch();
}
"""
            )
        slicer = WinyunqCodeSlicer()
        slicer._run_doxygen = lambda name, files: None
        self.editor = WinyunqTargetEditor(slicer)
        self.target = "AExampleActor::UpdateInstances"

    def tearDown(self):
        self.temporary_directory.cleanup()

    def prepare(self):
        return self.editor.prepare(self.target, self.root)["ticket"]

    def test_replace_changes_only_requested_code_and_preserves_comments(self):
        ticket = self.prepare()
        result = self.editor.replace(
            ticket,
            "CachedCount = Count;",
            "CachedCount = FMath::Max(Count, 0);",
        )
        with open(self.source_path, "r", encoding="utf-8") as stream:
            source = stream.read()
        self.assertEqual("applied", result["status"])
        self.assertIn("Keep this statement explanation", source)
        self.assertIn("CachedCount = FMath::Max(Count, 0);", source)
        self.assertIn("DoNotTouch();", source)

    def test_replace_rejects_comments_in_code_plane(self):
        with self.assertRaisesRegex(ValueError, "cannot contain comments"):
            self.editor.replace(
                self.prepare(),
                "CachedCount = Count;",
                "// explain\nCachedCount = Count + 1;",
            )

    def test_replace_rejects_range_that_crosses_existing_comment(self):
        with self.assertRaisesRegex(ValueError, "protected comment"):
            self.editor.replace(
                self.prepare(),
                "CachedCount = Count; NotifyChanged();",
                "RefreshEverything();",
            )

    def test_replace_rejects_stale_revision(self):
        ticket = self.prepare()
        with open(self.source_path, "a", encoding="utf-8") as stream:
            stream.write("\n// external change\n")
        with self.assertRaisesRegex(ValueError, "changed after Prepare"):
            self.editor.replace(ticket, "CachedCount = Count;", "CachedCount = 1;")

    def test_prepare_rejects_overloaded_target_without_signature(self):
        with open(self.source_path, "a", encoding="utf-8") as stream:
            stream.write(
                """
void AExampleActor::UpdateInstances(float Count)
{
    CachedCount = static_cast<int>(Count);
}
"""
            )
        with self.assertRaisesRegex(ValueError, "overloaded definitions"):
            self.prepare()


if __name__ == "__main__":
    unittest.main()
