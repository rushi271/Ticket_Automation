import argparse
from pathlib import Path
from typing import Any
from datetime import datetime, timezone

from batch_processor import CHASSIS_PATTERN, AIS140ApiClient, _resolve_base_urls, _resolve_login_candidates, write_error_log, log_to_csv
from batch_queue import INCOMING_DIR, PROCESSING_DIR, PROCESSED_DIR, RTO_PROCESSED_DIR, FAILED_DIR, ensure_folders, move_job_files, scan_jobs

DIRECT_RTO_HOLD_STATES = {"hp", "ka", "tn", "kl", "wb", "ml"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Process tickets for a specific state prefix or chassis and update RTO hold status when needed."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--state",
        help=(
            "State initials or prefix extracted from filenames (for example 'mh' or 'tn'). "
            "Only jobs matching this state will be processed."
        ),
    )
    group.add_argument(
        "--chassis",
        help=(
            "Single chassis number or comma-separated list of chassis numbers to update directly with RTO hold status."
        ),
    )
    group.add_argument(
        "--chassis-file",
        help=(
            "Path to a text file containing chassis numbers, one per line, to update directly with RTO hold status."
        ),
    )
    parser.add_argument(
        "--batch-limit",
        type=int,
        default=200,
        help="Maximum number of matching jobs to process in one run.",
    )
    return parser.parse_args()


def filter_jobs_by_state(jobs: list[dict[str, Any]], state: str) -> list[dict[str, Any]]:
    normalized_state = state.strip().lower()
    return [job for job in jobs if (job.get("state") or "").strip().lower() == normalized_state]


def process_jobs(client: AIS140ApiClient, jobs: list[dict[str, Any]], direct_update: bool = False) -> None:
    for job in jobs:
        chassis_no = job["chassis_no"]
        print(f"Processing chassis: {chassis_no} (state={job.get('state')})")
        ticket = client.get_ticket_by_chassis(chassis_no)
        print(f"Ticket matched: {ticket.get('ticketNo')} | VIN: {ticket.get('vinNo')}")

        if direct_update:
            rto_timestamp = datetime.now(timezone.utc).strftime("%d-%m-%Y")
            client.update_status_to_rto_hold(ticket=ticket, remark=rto_timestamp)
        else:
            client.complete_stages_1_to_4(
                ticket=ticket,
                vltd_file=job["vltd_file"],
                backend_file=job["backend_file"],
            )


def _parse_chassis_argument(value: str) -> list[str]:
    chassis_numbers = []

    for part in value.replace(",", " ").split():
        chassis = part.strip().upper()

        if not CHASSIS_PATTERN.fullmatch(chassis):
            print(f"Skipping invalid chassis: {chassis}")
            try:
                log_to_csv(chassis, "FAILED", "Invalid chassis format")
            except Exception as e:
                print(f"Logging failed: {e}")
            continue

        chassis_numbers.append(chassis)

    return chassis_numbers


def _load_chassis_list(path: Path) -> list[str]:
    
    file_path = Path(path)
    
    if not file_path.exists():
        raise FileNotFoundError(f"Chassis file not found: {file_path}")

    chassis_list: list[str] = []
    with file_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            value = line.strip()
            if not value or value.startswith("#"):
                continue
            for part in value.replace(",", " ").split():
                if part.strip():
                    chassis = part.strip().upper()

                    if not CHASSIS_PATTERN.fullmatch(chassis):
                        print(f"Skipping invalid chassis: {chassis}")
                        try:
                            log_to_csv(chassis, "FAILED", "Invalid chassis format")
                        except Exception as e:
                            print(f"Logging failed: {e}")
                        continue

                    chassis_list.append(chassis)
    return chassis_list


def _process_chassis_batch(client: AIS140ApiClient, chassis_numbers: list[str]) -> None:
    for chassis_no in chassis_numbers:
        try:
            print(f"Processing direct chassis: {chassis_no}")
            ticket = client.get_ticket_by_chassis(chassis_no)
            print(f"Ticket matched: {ticket.get('ticketNo')} | VIN: {ticket.get('vinNo')}")
            rto_timestamp = datetime.now(timezone.utc).strftime("%d-%m-%Y")
            client.update_status_to_rto_hold(
                ticket=ticket,
                remark=rto_timestamp,
            )
            try:
                log_to_csv(chassis_no, "SUCCESS")
            except Exception as e:
                print(f"Logging failed: {e}")
            print(f"Completed direct RTO hold update for chassis {chassis_no}.")
        except Exception as error:
            print(f"FAILED direct chassis: {chassis_no} -> {error}")
            try:
                log_to_csv(chassis_no, "FAILED", str(error))
            except Exception as e:
                print(f"Logging failed: {e}")
            continue


def main() -> None:
    args = parse_args()
    state_name = args.state.strip().lower() if args.state else ""

    ensure_folders()

    base_urls = _resolve_base_urls()
    login_candidates = _resolve_login_candidates()
    if not base_urls:
        raise ValueError("No API base URL could be resolved.")
    if not login_candidates:
        raise ValueError(
            "No API credentials found. Set API_USER_EMAIL/API_PASSWORD or TOOL_USERNAME/TOOL_PASSWORD."
        )

    client = AIS140ApiClient(
        base_urls=base_urls,
        login_candidates=login_candidates,
    )
    client.login()

    chassis_numbers: list[str] = []
    if args.chassis_file:
        chassis_numbers = _load_chassis_list(Path(args.chassis_file))
    elif args.chassis:
        chassis_numbers = _parse_chassis_argument(args.chassis)

    if chassis_numbers:
        _process_chassis_batch(client, chassis_numbers)
        return

    direct_update = state_name in DIRECT_RTO_HOLD_STATES
    all_jobs = scan_jobs(INCOMING_DIR)
    matching_jobs = filter_jobs_by_state(all_jobs, state_name)

    if not matching_jobs:
        print(f"No jobs found in incoming with state '{args.state}'.")
        return

    matching_jobs = matching_jobs[: args.batch_limit]

    reserved_jobs = []
    for job in matching_jobs:
        reserved_jobs.append(move_job_files(job, PROCESSING_DIR))

    if not reserved_jobs:
        print("No jobs were reserved for processing.")
        return

    if direct_update:
        print(
            f"State '{args.state}' uses direct RTO hold updates; backend certificate upload will be skipped."
        )

    print(
        f"Reserved {len(reserved_jobs)} job(s) for state '{args.state}'. Starting processing."
    )

    completed_dir = RTO_PROCESSED_DIR if direct_update else PROCESSED_DIR

    for job in reserved_jobs:
        try:
            process_jobs(client, [job], direct_update=direct_update)
            move_job_files(job, completed_dir)
            try:
                log_to_csv(job["chassis_no"], "SUCCESS")
            except Exception as e:
                print(f"Logging failed: {e}")
            print(f"SUCCESS: {job['chassis_no']}")
        except Exception as error:
            print(f"FAILED: {job['chassis_no']} -> {error}")
            write_error_log(job, error)
            try:
                log_to_csv(job["chassis_no"], "FAILED", str(error))
            except Exception as e:
                print(f"Logging failed: {e}")
            move_job_files(job, FAILED_DIR)


if __name__ == "__main__":
    main()
