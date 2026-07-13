import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "skills" / "mspm0-ccs" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import capture_example  # noqa: E402
import ccs_dss_debug  # noqa: E402


class CaptureExampleSafetyTests(unittest.TestCase):
    def test_rejects_unsafe_example_names(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            examples_dir = Path(temp_dir) / "examples"
            for name in ("../outside", "a/b", r"a\b", ".", "C:outside", ""):
                with self.subTest(name=name), self.assertRaises(SystemExit):
                    capture_example.resolve_example_destination(examples_dir, name)

    def test_accepts_simple_example_name_inside_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            examples_dir = Path(temp_dir) / "examples"
            destination = capture_example.resolve_example_destination(examples_dir, "uart-dma_1")
            self.assertEqual(destination, (examples_dir / "uart-dma_1").resolve())

    def test_rejects_examples_root_that_is_a_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            examples_dir = Path(temp_dir) / "examples"
            examples_dir.write_text("not a directory", encoding="utf-8")

            with self.assertRaisesRegex(SystemExit, "not a directory"):
                capture_example.resolve_example_destination(examples_dir, "uart-dma")

    def test_explicit_syscfg_must_stay_inside_project(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = root / "project"
            project.mkdir()
            outside = root / "outside.syscfg"
            outside.write_text("// outside", encoding="utf-8")

            with self.assertRaisesRegex(SystemExit, "must stay inside"):
                capture_example.find_syscfg(project.resolve(), str(outside))

    def test_explicit_syscfg_must_have_syscfg_suffix(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir).resolve()
            source = project / "main.c"
            source.write_text("int main(void) { return 0; }", encoding="utf-8")

            with self.assertRaisesRegex(SystemExit, "SysConfig file not found"):
                capture_example.find_syscfg(project, "main.c")


class CcsDssSelectionTests(unittest.TestCase):
    def test_multiple_ccxml_files_require_explicit_selection(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir)
            target_configs = project / "targetConfigs"
            target_configs.mkdir()
            (target_configs / "jlink.ccxml").touch()
            (target_configs / "xds110.ccxml").touch()

            with self.assertRaisesRegex(SystemExit, "--ccxml"):
                ccs_dss_debug.find_ccxml(project, None)

    def test_single_ccxml_is_selected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir)
            target_configs = project / "targetConfigs"
            target_configs.mkdir()
            expected = target_configs / "jlink.ccxml"
            expected.touch()

            self.assertEqual(ccs_dss_debug.find_ccxml(project, None), expected.resolve())

    def test_relative_explicit_ccxml_is_resolved_from_project(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir)
            target_configs = project / "targetConfigs"
            target_configs.mkdir()
            expected = target_configs / "jlink.ccxml"
            expected.touch()

            actual = ccs_dss_debug.find_ccxml(project, "targetConfigs/jlink.ccxml")
            self.assertEqual(actual, expected.resolve())

    def test_multiple_programs_require_explicit_selection_when_needed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir)
            debug = project / "Debug"
            release = project / "Release"
            debug.mkdir()
            release.mkdir()
            (debug / "firmware.out").touch()
            (release / "firmware.out").touch()

            with self.assertRaisesRegex(SystemExit, "--out"):
                ccs_dss_debug.find_program(project, None, required=True)

    def test_program_is_not_auto_selected_when_command_does_not_need_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir)
            debug = project / "Debug"
            debug.mkdir()
            (debug / "firmware.out").touch()

            self.assertIsNone(ccs_dss_debug.find_program(project, None, required=False))

    def test_relative_explicit_program_is_resolved_from_project(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir)
            debug = project / "Debug"
            debug.mkdir()
            expected = debug / "firmware.out"
            expected.touch()

            actual = ccs_dss_debug.find_program(project, "Debug/firmware.out", required=True)
            self.assertEqual(actual, expected.resolve())


if __name__ == "__main__":
    unittest.main()
