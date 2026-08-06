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


class TestWinyunqCodeSlicer(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = self.temporary_directory.name
        self.header_path = os.path.join(self.root, "ExampleActor.h")
        self.source_path = os.path.join(self.root, "ExampleActor.cpp")
        with open(self.header_path, "w", encoding="utf-8") as stream:
            stream.write(
                """/** Public actor contract. */
class AExampleActor
{
public:
    /**
     * @brief Updates the visible instances.
     * @param Count Number of instances.
     */
    void UpdateInstances(int Count);

private:
    int CachedCount = 0;
};
"""
            )
        with open(self.source_path, "w", encoding="utf-8") as stream:
            stream.write(
                """#include \"ExampleActor.h\"

/** Implementation detail. */
void AExampleActor::UpdateInstances(int Count)
{
    /// Preserve the previous count until validation succeeds.
    if (Count < 0)
    {
        return;
    }

    CachedCount = Count; // Commit the validated value.
}

void AExampleActor::UnrelatedFunction()
{
}
"""
            )

        self.slicer = WinyunqCodeSlicer()
        self.slicer._run_doxygen = lambda name, files: None

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_declaration_contains_contract_without_siblings(self):
        result = self.slicer.read(
            "AExampleActor::UpdateInstances", self.root, view="declaration"
        )
        self.assertIn("@brief Updates the visible instances.", result)
        self.assertIn("void UpdateInstances(int Count);", result)
        self.assertNotIn("CachedCount", result)

    def test_definition_removes_comments_and_sibling_functions(self):
        result = self.slicer.read(
            "AExampleActor::UpdateInstances", self.root, view="implementation"
        )
        self.assertIn("CachedCount = Count;", result)
        self.assertNotIn("Preserve the previous count", result)
        self.assertNotIn("Commit the validated value", result)
        self.assertNotIn("UnrelatedFunction", result)

    def test_exact_read_keeps_only_target_and_its_comments(self):
        result = self.slicer.read(
            "AExampleActor::UpdateInstances", self.root, view="exact"
        )
        self.assertIn("Preserve the previous count", result)
        self.assertIn("Commit the validated value", result)
        self.assertNotIn("UnrelatedFunction", result)

    def test_body_comment_view_does_not_repeat_public_documentation(self):
        result = self.slicer.read(
            "AExampleActor::UpdateInstances",
            self.root,
            view="comments",
            comment_part="body",
        )
        self.assertIn("Preserve the previous count", result)
        self.assertIn("Commit the validated value", result)
        self.assertNotIn("Updates the visible instances", result)

    def test_body_view_omits_redundant_signature_and_comment_gaps(self):
        result = self.slicer.read(
            "AExampleActor::UpdateInstances", self.root, view="body"
        )
        self.assertIn("CachedCount = Count;", result)
        self.assertNotIn("AExampleActor::UpdateInstances", result)
        self.assertNotIn("\n\n", result)


if __name__ == "__main__":
    unittest.main()
