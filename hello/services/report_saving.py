from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from hello.services.storage import save_report_to_s3


def _default(o: Any):
    try:
        return o.isoformat()
    except Exception:
        return str(o)


async def save_final_report_to_s3(
    report_payload: dict[str, Any], key_prefix: str = "reports/"
) -> str:
    """Serialize the report payload to bytes and upload to S3. Returns s3 path.

    This produces a compact but readable JSON artifact that the frontend can download.
    Replace this with PDF/PowerPoint generation later and reuse the same S3 helper.
    """
    envelope = {
        "saved_at": datetime.utcnow().isoformat() + "Z",
        "report": report_payload,
    }
    data = json.dumps(envelope, default=_default, separators=(",", ":")).encode("utf-8")
    s3_path = await save_report_to_s3(
        data,
        key_prefix=key_prefix,
        content_type="application/json",
    )
    return s3_path
