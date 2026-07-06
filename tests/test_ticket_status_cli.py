import unittest
from typing import Any

from batch_processor import AIS140ApiClient, ApiError, STAGE_FLOW
from ticket_status_cli import parse_args, resolve_status_code


class TicketStatusCliTests(unittest.TestCase):
    def test_resolve_status_code_accepts_exact_code(self) -> None:
        self.assertEqual(resolve_status_code("STS_CO_18"), "STS_CO_18")

    def test_resolve_status_code_maps_close_alias(self) -> None:
        self.assertEqual(resolve_status_code("close"), "STS_CO_18")

    def test_resolve_status_code_maps_on_hold_alias(self) -> None:
        self.assertEqual(resolve_status_code("on hold"), "STS_CO_17")

    def test_parse_args_accepts_status_code_without_status_alias(self) -> None:
        args = parse_args(["--chassis", "MAT805021TFD05775", "--status-code", "STS_CO_17"])
        self.assertEqual(args.chassis, "MAT805021TFD05775")
        self.assertEqual(args.status_code, "STS_CO_17")
        self.assertIsNone(args.status)

    def test_update_ticket_status_for_non_terminal_codes_only_runs_stage_1(self) -> None:
        class RecordingClient(AIS140ApiClient):
            def __init__(self) -> None:
                self.calls: list[tuple[str, str, str, str, str, str]] = []

            def _save_ticket_stage(
                self,
                *,
                ticket: dict[str, Any],
                stage: str,
                activity: str,
                associated: str,
                status_code: str,
                overall_status: str,
                remark: str,
                include_certificate_dates: bool = False,
            ) -> None:
                self.calls.append(
                    (stage, activity, associated, status_code, overall_status, remark)
                )

        ticket = {
            "ticketNo": "T-1",
            "imei": "IMEI",
            "vinNo": "VIN",
            "iccid": "ICCID",
        }

        client = RecordingClient()
        client.update_ticket_status(
            ticket,
            status_code="STS_CO_03",
            remark="manual update",
        )

        self.assertEqual(len(client.calls), len(STAGE_FLOW["Stage 1"]))
        self.assertTrue(all(call[0] == "Stage 1" for call in client.calls))
        self.assertTrue(all(call[3] == "STS_CO_06" for call in client.calls))
        self.assertTrue(all(call[4] == "STS_CO_03" for call in client.calls))
        self.assertTrue(all(call[5] == "manual update" for call in client.calls))

    def test_update_ticket_status_treats_already_progressed_errors_as_success(self) -> None:
        class RecordingClient(AIS140ApiClient):
            def __init__(self) -> None:
                self.calls: list[tuple[str, str, str, str, str, str]] = []

            def _save_ticket_stage(
                self,
                *,
                ticket: dict[str, Any],
                stage: str,
                activity: str,
                associated: str,
                status_code: str,
                overall_status: str,
                remark: str,
                include_certificate_dates: bool = False,
            ) -> None:
                self.calls.append(
                    (stage, activity, associated, status_code, overall_status, remark)
                )
                raise ApiError(
                    "POST /api/crm/saveTicketStage failed (HTTP 500): {'message': 'This activity cannot be updated because ticket has already progressed beyond it.', 'status': False}"
                )

        ticket = {
            "ticketNo": "T-1",
            "imei": "IMEI",
            "vinNo": "VIN",
            "iccid": "ICCID",
        }

        client = RecordingClient()
        client.update_ticket_status(
            ticket,
            status_code="STS_CO_23",
            remark="manual update",
        )

        self.assertEqual(
            len(client.calls),
            len(STAGE_FLOW["Stage 1"]) + len(STAGE_FLOW["Stage 2"]) + len(STAGE_FLOW["Stage 3"]) + 1,
        )

    def test_update_ticket_status_skips_prerequisite_incomplete_errors(self) -> None:
        class RecordingClient(AIS140ApiClient):
            def __init__(self) -> None:
                self.calls: list[tuple[str, str, str, str, str, str]] = []

            def _save_ticket_stage(
                self,
                *,
                ticket: dict[str, Any],
                stage: str,
                activity: str,
                associated: str,
                status_code: str,
                overall_status: str,
                remark: str,
                include_certificate_dates: bool = False,
            ) -> None:
                self.calls.append(
                    (stage, activity, associated, status_code, overall_status, remark)
                )
                raise ApiError(
                    "POST /api/crm/saveTicketStage failed (HTTP 500): {'message': 'Previous activity Stage 1 || FOTA / OTA Activities || Dealer Request / Vehicle Ignition On must be completed first.', 'status': False}"
                )

        ticket = {
            "ticketNo": "T-1",
            "imei": "IMEI",
            "vinNo": "VIN",
            "iccid": "ICCID",
        }

        client = RecordingClient()
        client.update_ticket_status(
            ticket,
            status_code="STS_CO_23",
            remark="manual update",
        )

        self.assertEqual(
            len(client.calls),
            len(STAGE_FLOW["Stage 1"]) + len(STAGE_FLOW["Stage 2"]) + len(STAGE_FLOW["Stage 3"]) + 1,
        )

    def test_terminal_status_uses_target_status_on_final_stage_update(self) -> None:
        class RecordingClient(AIS140ApiClient):
            def __init__(self) -> None:
                self.calls: list[tuple[str, str, str, str, str, str]] = []

            def _save_ticket_stage(
                self,
                *,
                ticket: dict[str, Any],
                stage: str,
                activity: str,
                associated: str,
                status_code: str,
                overall_status: str,
                remark: str,
                include_certificate_dates: bool = False,
            ) -> None:
                self.calls.append(
                    (stage, activity, associated, status_code, overall_status, remark)
                )

        ticket = {
            "ticketNo": "T-1",
            "imei": "IMEI",
            "vinNo": "VIN",
            "iccid": "ICCID",
        }

        client = RecordingClient()
        client.update_ticket_status(
            ticket,
            status_code="STS_CO_23",
            remark="manual update",
        )

        stage4_call = [call for call in client.calls if call[0] == "Stage 4"][0]
        self.assertEqual(stage4_call[3], "STS_CO_18")
        self.assertEqual(stage4_call[4], "STS_CO_18")


if __name__ == "__main__":
    unittest.main()
