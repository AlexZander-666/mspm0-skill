import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "skills" / "mspm0-ccs" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import detect_probe  # noqa: E402


class WindowsProbeDetectionTests(unittest.TestCase):
    @patch.object(detect_probe, "windows_serial_ports")
    @patch.object(detect_probe, "windows_pnp_devices")
    def test_detects_cmsis_dap_from_usbdevice_class_and_links_com_port(
        self, pnp_devices, serial_ports
    ) -> None:
        pnp_devices.return_value = [
            {
                "Class": "USBDevice",
                "FriendlyName": "Horco CMSIS-DAP v2",
                "Manufacturer": "WinUsb Device",
                "InstanceId": r"USB\VID_FAED&PID_4874&MI_00\6&20AC257D&0&0000",
            }
        ]
        serial_ports.return_value = [
            {
                "DeviceID": "COM4",
                "Name": "USB Serial Device (COM4)",
                "PNPDeviceID": r"USB\VID_FAED&PID_4874&MI_02\6&20AC257D&0&0002",
            }
        ]

        probes = detect_probe.detect_windows()

        self.assertEqual(len(probes), 1)
        self.assertEqual(probes[0].kind, "cmsis-dap")
        self.assertEqual(probes[0].usb_id, "FAED:4874")
        self.assertEqual(probes[0].serial_ports, ["COM4"])
        self.assertEqual(probes[0].recommended_config, "interface/cmsis-dap.cfg")

    @patch.object(detect_probe, "windows_serial_ports")
    @patch.object(detect_probe, "windows_pnp_devices")
    def test_deduplicates_composite_probe_interfaces_by_container_id(
        self, pnp_devices, serial_ports
    ) -> None:
        container_id = "{52718FBE-FD7A-547F-84E9-5DC59B030A2C}"
        pnp_devices.return_value = [
            {
                "Class": "USBDevice",
                "FriendlyName": "DAPLink CMSIS-DAP",
                "Manufacturer": "Arm",
                "InstanceId": r"USB\VID_0D28&PID_0204&MI_00\6&20AC257D&0&0000",
                "ContainerId": container_id,
            },
            {
                "Class": "Ports",
                "FriendlyName": "mbed Serial Port (COM4)",
                "Manufacturer": "Arm",
                "InstanceId": r"USB\VID_0D28&PID_0204&MI_02\6&20AC257D&0&0002",
                "ContainerId": container_id,
            },
        ]
        serial_ports.return_value = [
            {
                "DeviceID": "COM4",
                "Name": "mbed Serial Port (COM4)",
                "PNPDeviceID": r"USB\VID_0D28&PID_0204&MI_02\6&20AC257D&0&0002",
            }
        ]

        probes = detect_probe.detect_windows()

        self.assertEqual(len(probes), 1)
        self.assertEqual(probes[0].kind, "cmsis-dap")
        self.assertEqual(probes[0].serial_ports, ["COM4"])
        self.assertIn("DAPLink CMSIS-DAP", probes[0].evidence)
        self.assertIn("mbed Serial Port (COM4)", probes[0].evidence)

    @patch.object(detect_probe, "windows_serial_ports", return_value=[])
    @patch.object(detect_probe, "windows_pnp_devices")
    def test_keeps_identical_probe_models_with_different_containers_separate(
        self, pnp_devices, _serial_ports
    ) -> None:
        pnp_devices.return_value = [
            {
                "FriendlyName": "DAPLink CMSIS-DAP",
                "Manufacturer": "Arm",
                "InstanceId": r"USB\VID_0D28&PID_0204&MI_00\6&AAAA&0&0000",
                "ContainerId": "{11111111-1111-1111-1111-111111111111}",
            },
            {
                "FriendlyName": "DAPLink CMSIS-DAP",
                "Manufacturer": "Arm",
                "InstanceId": r"USB\VID_0D28&PID_0204&MI_00\6&BBBB&0&0000",
                "ContainerId": "{22222222-2222-2222-2222-222222222222}",
            },
        ]

        probes = detect_probe.detect_windows()

        self.assertEqual(len(probes), 2)

    @patch.object(detect_probe, "windows_serial_ports")
    @patch.object(detect_probe, "windows_pnp_devices")
    def test_detects_xds110_outside_usb_class(self, pnp_devices, serial_ports) -> None:
        pnp_devices.return_value = [
            {
                "Class": "Ports",
                "FriendlyName": "XDS110 Class Application/User UART (COM5)",
                "Manufacturer": "Texas Instruments",
                "InstanceId": r"USB\VID_0451&PID_BEF3&MI_02\7&123456&0&0002",
            }
        ]
        serial_ports.return_value = [
            {
                "DeviceID": "COM5",
                "Name": "XDS110 Class Application/User UART (COM5)",
                "PNPDeviceID": r"USB\VID_0451&PID_BEF3&MI_02\7&123456&0&0002",
            }
        ]

        probes = detect_probe.detect_windows()

        self.assertEqual(len(probes), 1)
        self.assertEqual(probes[0].kind, "xds110")
        self.assertEqual(probes[0].serial_ports, ["COM5"])

    @patch.object(detect_probe, "windows_serial_ports", return_value=[])
    @patch.object(detect_probe, "windows_pnp_devices")
    def test_detects_hid_class_cmsis_dap(self, pnp_devices, _serial_ports) -> None:
        pnp_devices.return_value = [
            {
                "Class": "HIDClass",
                "FriendlyName": "CMSIS-DAP",
                "Manufacturer": "Arm",
                "InstanceId": r"HID\VID_0D28&PID_0204&MI_03\8&123456&0&0000",
            }
        ]

        probes = detect_probe.detect_windows()

        self.assertEqual(len(probes), 1)
        self.assertEqual(probes[0].kind, "cmsis-dap")
        self.assertEqual(probes[0].usb_id, "0D28:0204")

    def test_empty_result_is_reported_as_inconclusive(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            detect_probe.print_text([])

        text = output.getvalue()
        self.assertIn("inconclusive", text)
        self.assertIn("not proof", text)
        self.assertIn("serial ports", text)

    @patch.object(detect_probe, "detect_probes", side_effect=RuntimeError("PnP failed"))
    def test_json_error_keeps_stable_top_level_schema(self, _detect_probes) -> None:
        output = io.StringIO()
        with patch.object(sys, "argv", ["detect_probe.py", "--json"]), redirect_stdout(output):
            exit_code = detect_probe.main()

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["probes"], [])
        self.assertEqual(payload["error"], "PnP failed")


if __name__ == "__main__":
    unittest.main()
