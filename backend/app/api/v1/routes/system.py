from __future__ import annotations

from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/status")
def feature_status() -> dict[str, object]:
    """Public, non-sensitive summary of which features this deployment has configured."""
    s = get_settings()
    return {
        "environment": s.app_env,
        "auth_mode": s.auth_mode,
        "storage_backend": s.storage_backend,
        "features": {
            "upload": True,
            "rendering": True,
            "transcription": {"available": False, "reason": "Planned for phase 2."},
            "ai_clip_discovery": {"available": False, "reason": "Planned for phase 2."},
            "captions": {"available": False, "reason": "Planned for phase 2."},
            "billing": {"available": False, "reason": "Stripe checkout is planned for phase 3."},
            "email": {"available": False, "reason": "Transactional email is planned for phase 3."},
            "url_import": {
                "available": False,
                "reason": "Direct upload is the supported input method.",
            },
            "social_publishing": {"available": False, "reason": "Planned for phase 4."},
        },
    }
