import re
from pathlib import Path

# PUT YOUR REAL LOCAL SYNCED FOLDER PATH HERE
INCOMING_DIR = Path(r"C:\Users\Rushi Mantri\Downloads\AIS Certificates\ACCOLADE ELECTRONICS PRIVATE LIMITED\aisautomation - Backend and VLTD Certificates\incoming")

# chassis starts with MAT and then 14 alphanumeric chars
CHASSIS_RE = re.compile(r"MAT[A-Z0-9]{14}", re.IGNORECASE)


def extract_chassis(file_path: Path) -> str:
    match = CHASSIS_RE.search(file_path.name)
    if not match:
        raise ValueError(f"Could not extract chassis from filename: {file_path.name}")
    return match.group(0).upper()


def detect_cert_type(file_path: Path) -> str:
    name = file_path.name.upper()

    if "VLTD" in name:
        return "vltd"
    if "NIC" in name or "BACKEND" in name:
        return "backend"

    raise ValueError(f"Could not detect certificate type from filename: {file_path.name}")


def scan_jobs(incoming_dir: Path):
    grouped = {}

    for file_path in incoming_dir.iterdir():
        if not file_path.is_file():
            continue

        if file_path.suffix.lower() != ".pdf":
            continue

        try:
            chassis = extract_chassis(file_path)
            cert_type = detect_cert_type(file_path)
        except Exception as e:
            print(f"Skipping {file_path.name}: {e}")
            continue

        if chassis not in grouped:
            grouped[chassis] = {}

        grouped[chassis][cert_type] = file_path

    jobs = []
    for chassis, files in grouped.items():
        if "vltd" in files and "backend" in files:
            jobs.append({
                "chassis_no": chassis,
                "vltd_file": files["vltd"],
                "backend_file": files["backend"],
            })

    return jobs


def main():
    print(f"Scanning folder: {INCOMING_DIR}")
    print()

    jobs = scan_jobs(INCOMING_DIR)

    if not jobs:
        print("No complete jobs found.")
        return

    print(f"Found {len(jobs)} complete job(s):\n")

    for i, job in enumerate(jobs, start=1):
        print(f"Job {i}")
        print(f"  Chassis     : {job['chassis_no']}")
        print(f"  VLTD file   : {job['vltd_file'].name}")
        print(f"  Backend file: {job['backend_file'].name}")
        print()


if __name__ == "__main__":
    main()