import unittest

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


if __name__ == "__main__":
    unittest.main()
