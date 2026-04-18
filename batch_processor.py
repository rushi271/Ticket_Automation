import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

from batch_queue import (
    reserve_jobs,
    PROCESSED_DIR,
    FAILED_DIR,
    ERROR_SCREENSHOTS_DIR,
)

load_dotenv()

DEFAULT_BASE_URLS = [
    "http://atcu-data.accoladeelectronics.com:6101",
    "http://aepl-tcu4g-qa.accoladeelectronics.com:6101",
]

GET_TICKET_LIST_PATH = "/api/crm/getAIS140TicketList"
LOGIN_PATH = "/api/user/login"
SAVE_STAGE_PATH = "/api/crm/saveTicketStage"
UPLOAD_VAHAN_CERT_PATH = "/api/crm/uploadVahanCertificate"
UPLOAD_BACKEND_CERT_PATH = "/api/crm/uploadBackendCertificate"

STATUS_STAGE_COMPLETED = "STS_CO_06"
STATUS_TICKET_CLOSED = "STS_CO_18"

STAGE_FLOW = {
    "Stage 1": [
        {
            "activity": "FOTA / OTA Activities",
            "associated": "Dealer Request / Vehicle Ignition On",
        },
        {
            "activity": "FOTA / OTA Activities",
            "associated": "GSM Network Availability",
        },
        {
            "activity": "FOTA / OTA Activities",
            "associated": "GPS Fix availability",
        },
    ],
    "Stage 2": [
        {
            "activity": "Vahan Certification",
            "associated": "Vahan Portal Availability",
        },
        {
            "activity": "Vahan Certification",
            "associated": "Vehicle Data availability on Vahan",
        },
    ],
    "Stage 3": [
        {
            "activity": "AIS-140 Certification",
            "associated": "Backend Portal Availability",
        },
        {
            "activity": "AIS-140 Certification",
            "associated": "Panic Event Confirmation",
        },
        {
            "activity": "AIS-140 Certification",
            "associated": "OTP / Live Location Fetching",
        },
    ],
    "Stage 4": [
        {
            "activity": "Certificate Generation / Submission",
            "associated": "AEPL",
        }
    ],
}


class ApiError(RuntimeError):
    """Raised when the AIS140 API call fails."""


@dataclass
class LoginContext:
    base_url: str
    email: str
    token: str
    user_ref: str


def _as_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _add_years(dt: datetime, years: int) -> datetime:
    try:
        return dt.replace(year=dt.year + years)
    except ValueError:
        return dt.replace(month=2, day=28, year=dt.year + years)


def _dedupe_non_empty(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()

    for value in values:
        normalized = value.strip().rstrip("/")
        if not normalized:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)

    return out


def _safe_json(response: requests.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return {"raw": response.text}


def _extract_token(payload: dict[str, Any]) -> str | None:
    token = payload.get("token")
    if token:
        return str(token)

    data = payload.get("data")
    if isinstance(data, dict) and data.get("token"):
        return str(data["token"])

    return None


def _extract_user_ref(payload: dict[str, Any]) -> str | None:
    data = payload.get("data")
    if not isinstance(data, dict):
        return None

    for key in ("id", "_id", "userRef"):
        value = data.get(key)
        if value:
            return str(value)
    return None


def _resolve_base_urls() -> list[str]:
    env_base = os.getenv("API_BASE_URL", "").strip()
    url_candidates = [env_base, *DEFAULT_BASE_URLS]

    if "aepl-tcu4g-qa.accoladeelectronics.com" in env_base:
        url_candidates.append("http://atcu-data.accoladeelectronics.com:6101")
    if "atcu-data.accoladeelectronics.com" in env_base:
        url_candidates.append("http://aepl-tcu4g-qa.accoladeelectronics.com:6101")

    return _dedupe_non_empty(url_candidates)


def _resolve_login_candidates() -> list[tuple[str, str]]:
    candidates = [
        (os.getenv("API_USER_EMAIL", "").strip(), os.getenv("API_PASSWORD", "").strip()),
        (os.getenv("TOOL_USERNAME", "").strip(), os.getenv("TOOL_PASSWORD", "").strip()),
    ]

    unique: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for email, password in candidates:
        if not email or not password:
            continue
        pair = (email, password)
        if pair in seen:
            continue
        seen.add(pair)
        unique.append(pair)

    return unique


def move_processing_job(job: dict[str, Any], target_dir: Path) -> dict[str, Any]:
    target_dir.mkdir(parents=True, exist_ok=True)

    new_vltd = target_dir / job["vltd_file"].name
    new_backend = target_dir / job["backend_file"].name

    shutil.move(str(job["vltd_file"]), str(new_vltd))
    shutil.move(str(job["backend_file"]), str(new_backend))

    return {
        "chassis_no": job["chassis_no"],
        "vltd_file": new_vltd,
        "backend_file": new_backend,
    }


class AIS140ApiClient:
    def __init__(
        self,
        *,
        base_urls: list[str],
        login_candidates: list[tuple[str, str]],
        kpi_card_selected: str = "PRO",
        cert_validity_years: int = 2,
        timeout_seconds: int = 30,
    ) -> None:
        self.base_urls = base_urls
        self.login_candidates = login_candidates
        self.kpi_card_selected = kpi_card_selected
        self.cert_validity_years = cert_validity_years
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()
        self.session.trust_env = False
        self.ctx: LoginContext | None = None

    def login(self) -> LoginContext:
        errors: list[str] = []

        for base_url in self.base_urls:
            for email, password in self.login_candidates:
                try:
                    resp = self.session.post(
                        f"{base_url}{LOGIN_PATH}",
                        json={"userEmail": email, "password": password},
                        timeout=self.timeout_seconds,
                    )
                except requests.RequestException as exc:
                    errors.append(f"{base_url} {email}: request failed ({exc})")
                    continue

                payload = _safe_json(resp)
                if resp.status_code != 200:
                    errors.append(f"{base_url} {email}: HTTP {resp.status_code} -> {payload}")
                    continue

                if isinstance(payload, dict) and not payload.get("status", False):
                    errors.append(f"{base_url} {email}: login rejected -> {payload}")
                    continue

                token = _extract_token(payload if isinstance(payload, dict) else {})
                user_ref = _extract_user_ref(payload if isinstance(payload, dict) else {})

                if not token:
                    errors.append(f"{base_url} {email}: token missing in login response -> {payload}")
                    continue
                if not user_ref:
                    errors.append(f"{base_url} {email}: user reference missing in login response -> {payload}")
                    continue

                self.ctx = LoginContext(base_url=base_url, email=email, token=token, user_ref=user_ref)
                print(f"Authenticated against {base_url} as {email}")
                return self.ctx

        raise ApiError("Unable to authenticate with any configured API base URL / credential pair.\n" + "\n".join(errors))

    def _ensure_login(self) -> None:
        if self.ctx is None:
            self.login()

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        retry_on_unauthorized: bool = True,
    ) -> dict[str, Any]:
        self._ensure_login()
        assert self.ctx is not None

        headers = {"token": self.ctx.token}
        response = self.session.request(
            method=method.upper(),
            url=f"{self.ctx.base_url}{path}",
            params=params,
            json=json_body,
            data=data,
            files=files,
            headers=headers,
            timeout=self.timeout_seconds,
        )

        if response.status_code == 401 and retry_on_unauthorized:
            self.login()
            return self._request(
                method,
                path,
                params=params,
                json_body=json_body,
                data=data,
                files=files,
                retry_on_unauthorized=False,
            )

        payload = _safe_json(response)
        if response.status_code >= 400:
            raise ApiError(f"{method} {path} failed (HTTP {response.status_code}): {payload}")

        if isinstance(payload, dict) and payload.get("status") is False:
            raise ApiError(f"{method} {path} rejected by API: {payload}")

        if not isinstance(payload, dict):
            raise ApiError(f"{method} {path} returned unexpected payload: {payload}")

        return payload

    def get_ticket_by_chassis(self, chassis_no: str) -> dict[str, Any]:
        payload = self._request(
            "GET",
            GET_TICKET_LIST_PATH,
            params={
                "page": 1,
                "size": 50,
                "search": chassis_no.strip(),
                "kpiCardSelected": self.kpi_card_selected,
            },
        )

        items: list[dict[str, Any]] = []
        data_wrapper = payload.get("data", {})
        if isinstance(data_wrapper, dict):
            maybe_items = data_wrapper.get("data", [])
            if isinstance(maybe_items, list):
                items = [x for x in maybe_items if isinstance(x, dict)]

        if not items:
            raise ApiError(f"No ticket found for chassis {chassis_no}")

        exact = [x for x in items if str(x.get("vinNo", "")).upper() == chassis_no.upper()]
        chosen = exact[0] if exact else items[0]

        required = ["ticketNo", "imei", "vinNo", "iccid"]
        missing = [key for key in required if not chosen.get(key)]
        if missing:
            raise ApiError(f"Ticket found for {chassis_no}, but required fields are missing: {missing}; ticket={chosen}")

        return chosen

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
        assert self.ctx is not None

        payload: dict[str, Any] = {
            "ticketNo": ticket["ticketNo"],
            "imei": ticket["imei"],
            "vinNo": ticket["vinNo"],
            "stage": stage,
            "activity": activity,
            "associated": associated,
            "status": status_code,
            "remark": remark,
            "remarkbyaccolade": overall_status,
            "userRef": self.ctx.user_ref,
        }

        if include_certificate_dates:
            start_dt = datetime.now(timezone.utc)
            end_dt = _add_years(start_dt, self.cert_validity_years)
            payload["certificateStartDate"] = _as_iso(start_dt)
            payload["certificateExpiryDate"] = _as_iso(end_dt)

        self._request("POST", SAVE_STAGE_PATH, json_body=payload)

    def complete_stages_1_to_3(self, ticket: dict[str, Any]) -> None:
        for stage in ("Stage 1", "Stage 2", "Stage 3"):
            for step in STAGE_FLOW[stage]:
                self._save_ticket_stage(
                    ticket=ticket,
                    stage=stage,
                    activity=step["activity"],
                    associated=step["associated"],
                    status_code=STATUS_STAGE_COMPLETED,
                    overall_status=STATUS_STAGE_COMPLETED,
                    remark="done",
                )

    def close_ticket_with_stage_4(self, ticket: dict[str, Any]) -> None:
        step = STAGE_FLOW["Stage 4"][0]
        self._save_ticket_stage(
            ticket=ticket,
            stage="Stage 4",
            activity=step["activity"],
            associated=step["associated"],
            status_code=STATUS_STAGE_COMPLETED,
            overall_status=STATUS_TICKET_CLOSED,
            remark="Ticket Completed and Closed",
            include_certificate_dates=True,
        )

    def _upload_certificate(self, path: str, ticket: dict[str, Any], file_path: Path) -> None:
        if not file_path.exists():
            raise FileNotFoundError(f"Certificate file not found: {file_path}")

        form_data = {
            "vinNo": str(ticket["vinNo"]),
            "iccid": str(ticket["iccid"]),
            "ticketNo": str(ticket["ticketNo"]),
        }

        with file_path.open("rb") as handle:
            files = {"certificate": (file_path.name, handle, "application/pdf")}
            self._request("POST", path, data=form_data, files=files)

    def upload_certificates(self, ticket: dict[str, Any], vltd_file: Path, backend_file: Path) -> None:
        self._upload_certificate(UPLOAD_VAHAN_CERT_PATH, ticket, vltd_file)
        self._upload_certificate(UPLOAD_BACKEND_CERT_PATH, ticket, backend_file)


def write_error_log(job: dict[str, Any], error: Exception) -> None:
    ERROR_SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    log_file = ERROR_SCREENSHOTS_DIR / f"error_{job['chassis_no']}.txt"
    payload = {
        "chassis_no": job["chassis_no"],
        "error": str(error),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    log_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def process_one_ticket(client: AIS140ApiClient, job: dict[str, Any]) -> None:
    chassis_no = job["chassis_no"]
    vltd_file = job["vltd_file"]
    backend_file = job["backend_file"]

    print(f"Processing chassis: {chassis_no}")
    ticket = client.get_ticket_by_chassis(chassis_no)

    print(f"Ticket matched: {ticket.get('ticketNo')} | VIN: {ticket.get('vinNo')}")
    client.complete_stages_1_to_3(ticket)
    client.upload_certificates(ticket, vltd_file, backend_file)
    client.close_ticket_with_stage_4(ticket)


def run() -> None:
    cert_validity_years = int(os.getenv("API_CERT_VALIDITY_YEARS", "2"))
    batch_limit = int(os.getenv("BATCH_LIMIT", "150"))
    kpi_card_selected = os.getenv("API_KPI_CARD_SELECTED", "PRO")

    jobs = reserve_jobs(batch_limit=batch_limit)
    if not jobs:
        print("No complete jobs available in incoming.")
        return

    base_urls = _resolve_base_urls()
    login_candidates = _resolve_login_candidates()

    if not base_urls:
        raise ValueError("No API base URL could be resolved.")
    if not login_candidates:
        raise ValueError("No API credentials found. Set API_USER_EMAIL/API_PASSWORD or TOOL_USERNAME/TOOL_PASSWORD.")

    client = AIS140ApiClient(
        base_urls=base_urls,
        login_candidates=login_candidates,
        kpi_card_selected=kpi_card_selected,
        cert_validity_years=cert_validity_years,
    )
    client.login()

    print(f"Reserved {len(jobs)} job(s). Starting API-based ticket processing.")

    for job in jobs:
        try:
            process_one_ticket(client, job)
            move_processing_job(job, PROCESSED_DIR)
            print(f"SUCCESS: {job['chassis_no']}")
        except Exception as error:
            print(f"FAILED: {job['chassis_no']} -> {error}")
            write_error_log(job, error)
            move_processing_job(job, FAILED_DIR)


if __name__ == "__main__":
    run()
