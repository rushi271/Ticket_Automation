import re
import shutil
from pathlib import Path
from naming_config import extract_components

BASE_DIR = Path(r"D:\ACCOLADE ELECTRONICS PRIVATE LIMITED\aisautomation - Backend and VLTD Certificates")

INCOMING_DIR = BASE_DIR / "incoming"
PROCESSING_DIR = BASE_DIR / "processing"
PROCESSED_DIR = BASE_DIR / "processed"
FAILED_DIR = BASE_DIR / "failed"
ERROR_SCREENSHOTS_DIR = BASE_DIR / "error_screenshots"

CHASSIS_RE = re.compile(r"MAT[A-Z0-9]{14}", re.IGNORECASE)


def scan_jobs(folder: Path):
    grouped = {}

    for file_path in folder.iterdir():
        if not file_path.is_file():
            continue

        if file_path.suffix.lower() != ".pdf":
            continue

        try:
            components = extract_components(file_path)
            chassis = components["chassis"]
            cert_type = components["cert_type"]
            state = components.get("state", "")
        except Exception as e:
            print(f"Skipping {file_path.name}: {e}")
            continue

        # Group only by chassis so mixed formats can pair
        key = chassis

        if key not in grouped:
            grouped[key] = {"state": state, "chassis": chassis}
        else:
            # If state is missing in existing entry but available now, keep it
            if not grouped[key].get("state") and state:
                grouped[key]["state"] = state

        grouped[key][cert_type] = file_path

    jobs = []
    for key, files in grouped.items():
        # Check if vltd exists
        if "vltd" in files:
            # Get all backend types (everything except vltd and the metadata keys)
            backend_types = {k: v for k, v in files.items() if k not in ["state", "chassis", "vltd"]}

            # For each backend type, create a job
            for backend_type, backend_file in backend_types.items():
                jobs.append({
                    "state": files["state"],
                    "chassis_no": files["chassis"],
                    "backend_type": backend_type,
                    "vltd_file": files["vltd"],
                    "backend_file": backend_file,
                })

    return jobs


def ensure_folders():
    PROCESSING_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    FAILED_DIR.mkdir(parents=True, exist_ok=True)


def move_job_files(job: dict, target_dir: Path) -> dict:
    target_dir.mkdir(parents=True, exist_ok=True)

    new_vltd = target_dir / job["vltd_file"].name
    new_backend = target_dir / job["backend_file"].name

    shutil.move(str(job["vltd_file"]), str(new_vltd))
    shutil.move(str(job["backend_file"]), str(new_backend))

    return {
        "state": job["state"],
        "chassis_no": job["chassis_no"],
        "backend_type": job["backend_type"],
        "vltd_file": new_vltd,
        "backend_file": new_backend,
    }


def reserve_jobs(batch_limit: int | None = None):
    jobs = scan_jobs(INCOMING_DIR)

    if batch_limit is not None:
        jobs = jobs[:batch_limit]

    reserved = []
    for job in jobs:
        moved_job = move_job_files(job, PROCESSING_DIR)
        reserved.append(moved_job)

    return reserved


def main():
    ensure_folders()

    reserved_jobs = reserve_jobs(batch_limit=10)

    if not reserved_jobs:
        print("No complete jobs available in incoming.")
        return

    print(f"Reserved {len(reserved_jobs)} job(s) into processing:\n")

    for i, job in enumerate(reserved_jobs, start=1):
        print(f"Job {i}")
        print(f"  Chassis     : {job['chassis_no']}")
        print(f"  VLTD file   : {job['vltd_file']}")
        print(f"  Backend file: {job['backend_file']}")
        print()


if __name__ == "__main__":
    main()