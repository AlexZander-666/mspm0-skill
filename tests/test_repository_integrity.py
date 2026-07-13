import json
import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = REPO_ROOT / "skills" / "mspm0-ccs"


class RepositoryIntegrityTests(unittest.TestCase):
    def test_skill_frontmatter_has_required_fields(self) -> None:
        text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        match = re.match(r"\A---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
        self.assertIsNotNone(match, "SKILL.md must start with YAML frontmatter")
        frontmatter = match.group(1)
        self.assertRegex(frontmatter, r"(?m)^name:\s*mspm0-ccs\s*$")
        self.assertRegex(frontmatter, r"(?m)^description:\s*\S.+$")

    def test_example_manifests_reference_existing_files(self) -> None:
        manifests = sorted((SKILL_DIR / "examples").glob("*/manifest.json"))
        self.assertTrue(manifests, "at least one packaged example is required")

        for manifest_path in manifests:
            with self.subTest(example=manifest_path.parent.name):
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                self.assertIsInstance(manifest, dict)
                self.assertEqual(manifest.get("name"), manifest_path.parent.name)

                syscfg = manifest.get("syscfg")
                self.assertIsInstance(syscfg, str)
                self.assertTrue((manifest_path.parent / syscfg).is_file(), syscfg)

                source_files = manifest.get("source_files")
                self.assertIsInstance(source_files, list)
                self.assertTrue(source_files, "source_files must not be empty")
                for source_file in source_files:
                    self.assertTrue((manifest_path.parent / source_file).is_file(), source_file)


if __name__ == "__main__":
    unittest.main()
