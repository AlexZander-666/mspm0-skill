import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "skills" / "mspm0-ccs" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import run_sysconfig  # noqa: E402
import check_syscfg  # noqa: E402


def write_product(root: Path, version: str = "2.11.00.07") -> Path:
    product = root / ".metadata" / "product.json"
    product.parent.mkdir(parents=True)
    product.write_text(
        json.dumps({"name": "mspm0_sdk", "version": version}),
        encoding="utf-8",
    )
    return product


def write_project(
    root: Path,
    *,
    tool_version: str = "1.26.2",
    sdk_version: str = "2.11.0.07",
) -> Path:
    project = root / "project"
    project.mkdir()
    (project / "empty.syscfg").write_text(
        "\n".join(
            (
                "/**",
                f' * @versions {{"tool":"{tool_version}+test"}}',
                " */",
                '//@v2CliArgs --device "MSPM0G3507" --package "LQFP-64(PM)"',
                'const SYSCTL = scripting.addModule("/ti/driverlib/SYSCTL");',
            )
        ),
        encoding="utf-8",
    )
    (project / ".cproject").write_text(
        "\n".join(
            (
                '<?xml version="1.0" encoding="UTF-8"?>',
                "<cproject>",
                '  <storageModule value="PRODUCTS=MSPM0-SDK:'
                f'{sdk_version};sysconfig:{tool_version};"/>',
                '  <toolChain superClass="com.ti.ccstudio.TMS470_TICLANG"/>',
                "</cproject>",
            )
        ),
        encoding="utf-8",
    )
    return project


def write_fake_cli(
    root: Path,
    *,
    version: str = "1.26.2+test",
    warning: bool = False,
    fail: bool = False,
    honor_strict: bool = True,
) -> Path:
    if os.name == "nt":
        path = root / "fake_sysconfig_cli.bat"
        warning_line = "echo WARNING: fake warning 1>&2" if warning else ""
        strict_line = (
            'if "%strict%"=="1" exit /b 1'
            if warning and honor_strict
            else ""
        )
        fail_line = "exit /b 1" if fail else "exit /b 0"
        path.write_text(
            "\n".join(
                (
                    "@echo off",
                    f'if "%~1"=="--version" (echo {version}& exit /b 0)',
                    "set output=",
                    "set strict=0",
                    ":loop",
                    'if "%~1"=="" goto done',
                    'if "%~1"=="--output" (set output=%~2& shift& shift& goto loop)',
                    'if "%~1"=="--treatWarningsAsErrors" set strict=1',
                    "shift",
                    "goto loop",
                    ":done",
                    'if not exist "%output%" mkdir "%output%"',
                    'echo generated>"%output%\\ti_msp_dl_config.h"',
                    warning_line,
                    strict_line,
                    fail_line,
                )
            ),
            encoding="utf-8",
        )
    else:
        path = root / "fake_sysconfig_cli"
        warning_line = 'echo "WARNING: fake warning" >&2' if warning else ""
        strict_line = (
            '[ "$strict" -eq 1 ] && exit 1'
            if warning and honor_strict
            else ""
        )
        fail_line = "exit 1" if fail else "exit 0"
        path.write_text(
            "\n".join(
                (
                    "#!/bin/sh",
                    f'if [ "$1" = "--version" ]; then echo "{version}"; exit 0; fi',
                    'output=""',
                    "strict=0",
                    'while [ "$#" -gt 0 ]; do',
                    '  case "$1" in',
                    '    --output) output="$2"; shift 2 ;;',
                    '    --treatWarningsAsErrors) strict=1; shift ;;',
                    '    *) shift ;;',
                    "  esac",
                    "done",
                    'mkdir -p "$output"',
                    'echo generated > "$output/ti_msp_dl_config.h"',
                    warning_line,
                    strict_line,
                    fail_line,
                )
            ),
            encoding="utf-8",
        )
        path.chmod(0o755)
    return path


class MetadataTests(unittest.TestCase):
    def test_v2_args_override_legacy_args_and_versions_parse(self) -> None:
        metadata = run_sysconfig.parse_syscfg_metadata(
            "\n".join(
                (
                    '//@cliArgs --device "MSPM0G350X" --product "mspm0_sdk@2.10.00.04"',
                    '//@v2CliArgs --device "MSPM0G3507" --package "LQFP-64(PM)"',
                    '// @versions {"tool":"1.28.0+4712"}',
                )
            )
        )
        self.assertEqual(metadata["effective_args"]["device"], "MSPM0G3507")
        self.assertEqual(metadata["effective_args"]["package"], "LQFP-64(PM)")
        self.assertEqual(metadata["effective_args"]["product"], "mspm0_sdk@2.10.00.04")
        self.assertEqual(metadata["tool_version"], "1.28.0+4712")

    def test_ccs_products_and_compiler_parse(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project = write_project(Path(temp_dir))
            result = run_sysconfig.inspect_ccs_project(project)
        self.assertEqual(result["products"]["MSPM0-SDK"], "2.11.0.07")
        self.assertEqual(result["products"]["sysconfig"], "1.26.2")
        self.assertEqual(result["compiler"], "ticlang")

    def test_versions_ignore_leading_zero_differences(self) -> None:
        self.assertTrue(run_sysconfig.versions_match("2.11.0.07", "2.11.00.07"))
        self.assertTrue(run_sysconfig.versions_match("1.26.2", "1.26.2+4477"))


class SelectionSafetyTests(unittest.TestCase):
    def test_multiple_syscfg_files_require_explicit_selection(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir)
            (project / "one.syscfg").touch()
            (project / "two.syscfg").touch()
            with self.assertRaisesRegex(run_sysconfig.ResolutionError, "--script"):
                run_sysconfig.find_syscfg(project.resolve(), None)

    def test_explicit_syscfg_must_stay_inside_project(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = root / "project"
            project.mkdir()
            outside = root / "outside.syscfg"
            outside.touch()
            with self.assertRaisesRegex(run_sysconfig.ResolutionError, "stay inside"):
                run_sysconfig.find_syscfg(project.resolve(), str(outside))

    def test_project_version_selects_matching_tool_not_newest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project = write_project(Path(temp_dir))
            info = run_sysconfig.inspect_project(project)
            candidates = [
                run_sysconfig.ToolCandidate("/tools/1.26", "1.26.2+4477", "test"),
                run_sysconfig.ToolCandidate("/tools/1.28", "1.28.0+4712", "test"),
            ]
            with mock.patch.object(run_sysconfig, "discover_tools", return_value=candidates):
                selected, warnings, _available = run_sysconfig.select_tool(info, None)
        self.assertEqual(selected.version, "1.26.2+4477")
        self.assertEqual(warnings, [])

    def test_multiple_tools_without_declared_version_require_explicit_choice(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir) / "project"
            project.mkdir()
            (project / "empty.syscfg").write_text("// no version metadata", encoding="utf-8")
            info = run_sysconfig.inspect_project(project)
            candidates = [
                run_sysconfig.ToolCandidate("/tools/1.26", "1.26.2+4477", "test"),
                run_sysconfig.ToolCandidate("/tools/1.28", "1.28.0+4712", "test"),
            ]
            with mock.patch.object(run_sysconfig, "discover_tools", return_value=candidates):
                with self.assertRaisesRegex(run_sysconfig.ResolutionError, "--tool"):
                    run_sysconfig.select_tool(info, None)

    def test_conflicting_tool_declarations_require_explicit_choice(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project = write_project(Path(temp_dir), tool_version="1.26.2")
            syscfg = project / "empty.syscfg"
            syscfg.write_text(
                syscfg.read_text(encoding="utf-8").replace("1.26.2+test", "1.28.0+test"),
                encoding="utf-8",
            )
            info = run_sysconfig.inspect_project(project)
            candidates = [
                run_sysconfig.ToolCandidate("/tools/1.26", "1.26.2+4477", "test"),
                run_sysconfig.ToolCandidate("/tools/1.28", "1.28.0+4712", "test"),
            ]
            with mock.patch.object(run_sysconfig, "discover_tools", return_value=candidates):
                with self.assertRaisesRegex(run_sysconfig.ResolutionError, "conflicting"):
                    run_sysconfig.select_tool(info, None)

    def test_product_version_matches_with_different_zero_padding(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = write_project(root)
            info = run_sysconfig.inspect_project(project)
            product = write_product(root / "sdk", "2.11.00.07")
            candidate = run_sysconfig.product_from_json(product, "test")
            with mock.patch.object(run_sysconfig, "discover_products", return_value=[candidate]):
                selected, warnings, _available = run_sysconfig.select_product(info, None)
        self.assertEqual(selected.version, "2.11.00.07")
        self.assertEqual(warnings, [])


class CliExecutionTests(unittest.TestCase):
    def run_main(self, argv: list[str]) -> tuple[int, dict[str, object], str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = run_sysconfig.main(argv)
        return code, json.loads(stdout.getvalue()), stderr.getvalue()

    def test_explicit_newer_tool_warns_and_dry_run_does_not_generate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = write_project(root)
            tool = write_fake_cli(root, version="1.28.0+4712")
            product = write_product(root / "sdk")
            code, report, _stderr = self.run_main(
                [
                    str(project),
                    "--tool",
                    str(tool),
                    "--product",
                    str(product),
                    "--dry-run",
                    "--json",
                ]
            )
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "dry-run")
        self.assertTrue(any("differs" in item for item in report["warnings"]))
        self.assertEqual(report["generated_files"], [])

    def test_explicit_newer_tool_generation_has_warning_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = write_project(root)
            tool = write_fake_cli(root, version="1.28.0+4712")
            product = write_product(root / "sdk")
            code, report, _stderr = self.run_main(
                [
                    str(project),
                    "--tool",
                    str(tool),
                    "--product",
                    str(product),
                    "--json",
                ]
            )
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "warning")
        self.assertTrue(any("differs" in item for item in report["warnings"]))

    def test_generation_is_isolated_and_keep_output_can_be_inspected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = write_project(root)
            tool_dir = root / "tool dir"
            tool_dir.mkdir()
            tool = write_fake_cli(tool_dir)
            product = write_product(root / "sdk")
            code, report, _stderr = self.run_main(
                [
                    str(project),
                    "--tool",
                    str(tool),
                    "--product",
                    str(product),
                    "--keep-output",
                    "--json",
                ]
            )
            output = Path(report["output"]["path"])
            try:
                self.assertEqual(code, 0)
                self.assertEqual(report["status"], "ok")
                self.assertIn("ti_msp_dl_config.h", report["generated_files"])
                self.assertTrue((output / "ti_msp_dl_config.h").is_file())
                self.assertFalse((project / "ti_msp_dl_config.h").exists())
            finally:
                shutil.rmtree(output, ignore_errors=True)

    def test_default_temporary_output_is_removed_after_reporting(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = write_project(root)
            tool = write_fake_cli(root)
            product = write_product(root / "sdk")
            code, report, _stderr = self.run_main(
                [
                    str(project),
                    "--tool",
                    str(tool),
                    "--product",
                    str(product),
                    "--json",
                ]
            )
            output = Path(report["output"]["path"])
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "ok")
        self.assertFalse(output.exists())

    def test_warning_and_failure_statuses_are_distinct(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = write_project(root)
            product = write_product(root / "sdk")
            warning_tool = write_fake_cli(root, warning=True)
            code, report, _stderr = self.run_main(
                [
                    str(project),
                    "--tool",
                    str(warning_tool),
                    "--product",
                    str(product),
                    "--json",
                ]
            )
            self.assertEqual(code, 0)
            self.assertEqual(report["status"], "warning")

            failing_tool = write_fake_cli(root, version="1.26.2+failed", fail=True)
            code, report, _stderr = self.run_main(
                [
                    str(project),
                    "--tool",
                    str(failing_tool),
                    "--product",
                    str(product),
                    "--json",
                ]
            )
            self.assertEqual(code, 1)
            self.assertEqual(report["status"], "error")

    def test_strict_turns_cli_warning_into_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = write_project(root)
            product = write_product(root / "sdk")
            warning_tool = write_fake_cli(root, warning=True)
            code, report, _stderr = self.run_main(
                [
                    str(project),
                    "--tool",
                    str(warning_tool),
                    "--product",
                    str(product),
                    "--strict",
                    "--json",
                ]
            )
        self.assertEqual(code, 1)
        self.assertEqual(report["status"], "error")
        self.assertIn("--treatWarningsAsErrors", report["command_text"])

    def test_strict_fails_even_when_cli_ignores_warnings_as_errors(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = write_project(root)
            product = write_product(root / "sdk")
            warning_tool = write_fake_cli(root, warning=True, honor_strict=False)
            code, report, _stderr = self.run_main(
                [
                    str(project),
                    "--tool",
                    str(warning_tool),
                    "--product",
                    str(product),
                    "--strict",
                    "--json",
                ]
            )
        self.assertEqual(report["returncode"], 0)
        self.assertEqual(code, 1)
        self.assertEqual(report["status"], "error")


class CheckerIntegrationTests(unittest.TestCase):
    def test_checker_reports_ccs_products_and_unified_validation_hint(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project = write_project(Path(temp_dir))
            messages, details = check_syscfg.check_project(project)
        self.assertEqual(details["ccs_project"]["products"]["sysconfig"], "1.26.2")
        self.assertTrue(
            any("CCS 工程声明产品" in message.text for message in messages),
            messages,
        )
        self.assertIn("run_sysconfig.py", details["validation_hints"]["sysconfig_validate"])


if __name__ == "__main__":
    unittest.main()
