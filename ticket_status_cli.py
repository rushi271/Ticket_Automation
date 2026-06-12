import argparse
import re
from pathlib import Path
from typing import Any

from batch_processor import (
    AIS140ApiClient,
    CHASSIS_PATTERN,
    STATUS_TICKET_CLOSED,
    _resolve_base_urls,
    _resolve_login_candidates,
    log_to_csv,
)
from batch_queue import ensure_folders

STATUS_ALIASES = {
    "close": "STS_CO_18",
    "closed": "STS_CO_18",
    "completed": "STS_CO_06",
    "started": "STS_CO_03",
    "in-progress": "STS_CO_05",
    "on-hold": "STS_CO_17",
    "hold": "STS_CO_17",
    "rto-hold": "STS_CO_17",
    "rto": "STS_CO_17",
    "cancel": "STS_CO_20",
    "cancelled": "STS_CO_20",
}


def resolve_status_code(status: str) -> str:
    value = (status or "").strip()
    if not value:
        raise ValueError("Status cannot be empty")

    if value.upper().startswith("STS_CO_"):
        return value.upper()

    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if normalized in STATUS_ALIASES:
        return STATUS_ALIASES[normalized]

    if normalized.startswith("sts-co-"):
        return f"STS_CO_{normalized.split('-')[-1]}".upper()

    raise ValueError(
        f"Unsupported status '{status}'. Use a friendly value such as 'close' or 'on-hold', or pass an exact code like STS_CO_18."
    )


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Update a ticket to a target status by chassis number using a single command-line entry point."
    )
    parser.add_argument("--chassis", help="Single chassis number or a comma-separated list of chassis numbers.")
    parser.add_argument("--chassis-file", help="Path to a text file containing one chassis number per line.")
    parser.add_argument("--status", help="Friendly status such as 'close' or 'on-hold', or an exact code like 'STS_CO_18'.")
    parser.add_argument("--status-code", help="Exact status code such as STS_CO_17 or STS_CO_18. Overrides --status when provided.")
    parser.add_argument("--remark", default="Manual ticket status update", help="Remark to send with the status update.")
    parser.add_argument("--dry-run", action="store_true", help="Print the planned updates without sending them to the ticketing tool.")
    parsed_args = parser.parse_args(args)
    if not parsed_args.status and not parsed_args.status_code:
        parser.error("one of the arguments --status or --status-code is required")
    return parsed_args


def _parse_chassis_argument(value: str) -> list[str]:
    chassis_numbers: list[str] = []
    for part in value.replace(",", " ").split():
        chassis = part.strip().upper()
        if not CHASSIS_PATTERN.fullmatch(chassis):
            print(f"Skipping invalid chassis: {chassis}")
            continue
        chassis_numbers.append(chassis)
    return chassis_numbers


def _load_chassis_list(path: Path) -> list[str]:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Chassis file not found: {file_path}")

    chassis_numbers: list[str] = []
    with file_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            value = line.strip()
            if not value or value.startswith("#"):
                continue
            for part in value.replace(",", " ").split():
                chassis = part.strip().upper()
                if not CHASSIS_PATTERN.fullmatch(chassis):
                    print(f"Skipping invalid chassis: {chassis}")
                    continue
                chassis_numbers.append(chassis)
    return chassis_numbers


def _collect_chassis_numbers(args: argparse.Namespace) -> list[str]:
    if args.chassis_file:
        return _load_chassis_list(Path(args.chassis_file))
    if args.chassis:
        return _parse_chassis_argument(args.chassis)
    return []


def update_status_for_chassis(
    client: AIS140ApiClient,
    chassis_no: str,
    *,
    status_code: str,
    remark: str,
    dry_run: bool = False,
) -> None:
    print(f"Processing chassis: {chassis_no}")
    ticket = client.get_ticket_by_chassis(chassis_no)
    print(f"Ticket matched: {ticket.get('ticketNo')} | VIN: {ticket.get('vinNo')}")

    if dry_run:
        print(f"Dry run: would update ticket {ticket.get('ticketNo')} to status {status_code}")
        return

    include_certificate_dates = status_code == STATUS_TICKET_CLOSED
    client.update_ticket_status(
        ticket=ticket,
        status_code=status_code,
        remark=remark,
        include_certificate_dates=include_certificate_dates,
    )

    try:
        log_to_csv(chassis_no, "SUCCESS")
    except Exception as error:  # pragma: no cover - best effort logging
        print(f"Logging failed: {error}")


def main() -> None:
    args = parse_args()
    ensure_folders()

    status_code = resolve_status_code(args.status_code or args.status)
    chassis_numbers = _collect_chassis_numbers(args)
    if not chassis_numbers:
        raise ValueError("No valid chassis numbers were provided. Use --chassis or --chassis-file.")

    if args.dry_run:
        for chassis_no in chassis_numbers:
            print(f"Dry run: would update chassis {chassis_no} to status {status_code}")
        return

    base_urls = _resolve_base_urls()
    login_candidates = _resolve_login_candidates()
    if not base_urls:
        raise ValueError("No API base URL could be resolved.")
    if not login_candidates:
        raise ValueError("No API credentials found. Set API_USER_EMAIL/API_PASSWORD or TOOL_USERNAME/TOOL_PASSWORD.")

    client = AIS140ApiClient(base_urls=base_urls, login_candidates=login_candidates)
    client.login()

    for chassis_no in chassis_numbers:
        try:
            update_status_for_chassis(
                client,
                chassis_no,
                status_code=status_code,
                remark=args.remark,
                dry_run=False,
            )
            print(f"SUCCESS: {chassis_no}")
        except Exception as error:
            print(f"FAILED: {chassis_no} -> {error}")
            try:
                log_to_csv(chassis_no, "FAILED", str(error))
            except Exception as log_error:  # pragma: no cover - best effort logging
                print(f"Logging failed: {log_error}")


if __name__ == "__main__":
    main()
