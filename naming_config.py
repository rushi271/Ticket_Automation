import re
from pathlib import Path

PATTERNS = [
    {
        "format": "state_prefixed",
        "pattern": r"^([a-z]{2})\s*[-_]\s*(MAT[A-Z0-9]{14})(?:\s*[-_]\s*([A-Za-z0-9][A-Za-z0-9 ]*))?\s*\.pdf$",
        "groups": {"state": 1, "chassis": 2},
    },
    {
        "format": "simple",
        "pattern": r"^(MAT[A-Z0-9]{14})(?:\s*[-_]\s*([A-Za-z0-9][A-Za-z0-9 ]*))?\s*\.pdf$",
        "groups": {"chassis": 1},
    },
    {
        "format": "simple_space_suffix",
        "pattern": r"^(MAT[A-Z0-9]{14})\s+([A-Za-z0-9][A-Za-z0-9 ]*)\s*\.pdf$",
        "groups": {"chassis": 1},
    },
]


STATE_CODES = {"hp", "ka", "tn", "kl", "wb", "ml"}


def extract_backend_suffix(filename: str) -> str:
    suffix_match = re.search(
        r'(?:[-_]\s*|\s+)([A-Za-z0-9][A-Za-z0-9 ]*)\s*\.pdf$',
        filename.strip()
    )

    if suffix_match:
        extracted = suffix_match.group(1).strip()

        # Avoid treating chassis itself as suffix
        if re.fullmatch(r"MAT[A-Z0-9]{14}", extracted, re.IGNORECASE):
            return ""

        return extracted

    return ""


def extract_components(file_path: Path) -> dict:
    filename = file_path.name.strip()

    for pattern_config in PATTERNS:
        match = re.search(
            pattern_config["pattern"],
            filename,
            re.IGNORECASE
        )

        if match:
            result = {}

            for key, group_num in pattern_config["groups"].items():
                value = match.group(group_num).strip()
                result[key] = value.upper() if key == "chassis" else value.lower()

            suffix = extract_backend_suffix(filename)
            result["backend_suffix"] = suffix

            # Check if filename contains ONLY chassis number
            only_chassis = re.fullmatch(
                r"(MAT[A-Z0-9]{14})\.pdf",
                filename,
                re.IGNORECASE
            )

            normalized_suffix = suffix.lower()
            if only_chassis:
                result["cert_type"] = "vltd"
            elif "vltd" in normalized_suffix:
                result["cert_type"] = "vltd"
            elif normalized_suffix in STATE_CODES:
                if not result.get("state"):
                    result["state"] = normalized_suffix
                result["cert_type"] = "state_code"
            elif suffix:
                result["cert_type"] = "backend"
            else:
                result["cert_type"] = "backend"

            result["format"] = pattern_config["format"]
            return result

    raise ValueError(
        f"Filename '{file_path.name.strip()}' doesn't match any known format."
    )