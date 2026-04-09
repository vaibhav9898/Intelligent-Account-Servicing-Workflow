import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from secrets import token_hex
from typing import Any, Dict

from app.core.config import AUDIT_LOG, FILENET_DIR


def write_audit(event: str, correlation_id: str, payload: Dict[str, Any]) -> None:
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "correlation_id": correlation_id,
        "payload": payload,
    }
    with AUDIT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=True) + "\n")


def parse_document_text(upload_path: Path) -> Dict[str, str]:
    text = upload_path.read_text(encoding="utf-8", errors="ignore")
    extracted_old = ""
    extracted_new = ""

    for line in text.splitlines():
        raw = line.strip()
        lower = raw.lower()
        if ("bride" in lower or "old name" in lower) and ":" in raw:
            extracted_old = raw.split(":", 1)[1].strip()
        if ("married" in lower or "new name" in lower) and ":" in raw:
            extracted_new = raw.split(":", 1)[1].strip()

    authenticity_flag = "PASS" if len(text.strip()) > 20 else "FLAG"

    return {
        "old_name_extracted": extracted_old,
        "new_name_extracted": extracted_new,
        "authenticity_flag": authenticity_flag,
    }


def score_fields(
    request_old: str,
    request_new: str,
    extracted_old: str,
    extracted_new: str,
    authenticity_flag: str,
) -> Dict[str, Any]:
    old_match = request_old.strip().lower() == (extracted_old or "").strip().lower()
    new_match = request_new.strip().lower() == (extracted_new or "").strip().lower()

    confidence_old = 97 if old_match else 45
    confidence_new = 97 if new_match else 40
    confidence_auth = 85 if authenticity_flag == "PASS" else 55

    forgery_check = "PASS" if confidence_auth >= 80 else "FLAG"
    recommended_action = (
        "APPROVE"
        if confidence_old >= 90 and confidence_new >= 90 and forgery_check == "PASS"
        else "REVIEW"
    )

    return {
        "confidence_old_name": float(confidence_old),
        "confidence_new_name": float(confidence_new),
        "confidence_authenticity": float(confidence_auth),
        "forgery_check": forgery_check,
        "recommended_action": recommended_action,
    }


def generate_summary(
    customer_id: str,
    old_requested: str,
    new_requested: str,
    old_extracted: str,
    new_extracted: str,
    score_card: Dict[str, Any],
) -> str:
    return (
        f"Customer {customer_id} requested legal name change from '{old_requested}' "
        f"to '{new_requested}'. Extracted document values are old name "
        f"'{old_extracted or 'N/A'}' and new name '{new_extracted or 'N/A'}'. "
        f"Confidence scores: old={int(score_card['confidence_old_name'])}, "
        f"new={int(score_card['confidence_new_name'])}, "
        f"authenticity={int(score_card['confidence_authenticity'])}. "
        f"Forgery check={score_card['forgery_check']}. "
        f"Recommended action={score_card['recommended_action']}."
    )


def archive_to_filenet_mock(upload_path: Path, correlation_id: str) -> str:
    filenet_id = f"FN-{token_hex(5).upper()}"
    archived_name = f"{filenet_id}-{upload_path.name}"
    archived_path = FILENET_DIR / archived_name
    shutil.copy(upload_path, archived_path)

    metadata = {
        "filenet_reference_id": filenet_id,
        "source_filename": upload_path.name,
        "archived_path": str(archived_path),
        "correlation_id": correlation_id,
        "archived_at": datetime.now(timezone.utc).isoformat(),
    }
    metadata_path = FILENET_DIR / f"{filenet_id}.json"
    with metadata_path.open("w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=True, indent=2)

    return filenet_id


def mock_rps_write(customer_id: str, new_name: str, correlation_id: str) -> str:
    rps_reference = f"RPS-{token_hex(5).upper()}"
    write_audit(
        "rps_write_executed",
        correlation_id,
        {
            "customer_id": customer_id,
            "new_name": new_name,
            "rps_write_reference": rps_reference,
        },
    )
    return rps_reference
