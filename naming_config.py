import re
from pathlib import Path

PATTERNS = [
    {
        "format": "state_prefixed",
        "pattern": r"^([a-z]{2})\s*[-_]\s*(MAT[A-Z0-9]{14})(?:\s*[-_]\s*([A-Za-z0-9]+))?\s*\.pdf$",
        "groups": {"state": 1, "chassis": 2},
    },
    {
        "format": "simple",
        "pattern": r"^(MAT[A-Z0-9]{14})(?:\s*[-_]\s*([A-Za-z0-9]+))?\s*\.pdf$",
        "groups": {"chassis": 1},
    },
    {
        "format": "simple_space_suffix",
        "pattern": r"^(MAT[A-Z0-9]{14})\s+([A-Za-z0-9]+)\s*\.pdf$",
        "groups": {"chassis": 1},
    },
]

def extract_backend_suffix(filename: str) -> str:
    suffix_match = re.search(r'(?:[-_]\s*|\s+)([A-Za-z0-9]+)\s*\.pdf$', filename.strip())
    if suffix_match:
        return suffix_match.group(1)
    return ""

def extract_components(file_path: Path) -> dict:
    filename = file_path.name.strip()

    for pattern_config in PATTERNS:
        match = re.search(pattern_config["pattern"], filename, re.IGNORECASE)

        if match:
            result = {}

            for key, group_num in pattern_config["groups"].items():
                value = match.group(group_num).strip()
                result[key] = value.upper() if key == "chassis" else value.lower()

            suffix = extract_backend_suffix(filename)
            result["backend_suffix"] = suffix

            # If suffix contains 'vltd' anywhere, treat as VLTD
            if "vltd" in suffix.lower():
                result["cert_type"] = "vltd"
            elif suffix:
                result["cert_type"] = "backend"
            else:
                result["cert_type"] = "backend"

            result["format"] = pattern_config["format"]
            return result

    raise ValueError(
        f"Filename '{file_path.name.strip()}' doesn't match any known format."
    )