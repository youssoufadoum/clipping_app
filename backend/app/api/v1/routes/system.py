from __future__ import annotations

from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter(prefix="/system", tags=["system"])


def _ai(configured: bool) -> dict[str, object]:
    if configured:
        return {"available": True, "provider": "gemini"}
    return {"available": False, "reason": "GEMINI_API_KEY is not configured on this server."}


@router.get("/status")
def feature_status() -> dict[str, object]:
    """Public, non-sensitive summary of which features this deployment has configured."""
    s = get_settings()
    return {
        "environment": s.app_env,
        "auth_mode": s.auth_mode,
        "ai_available": s.ai_configured,
        "storage_backend": s.storage_backend,
        "features": {
            "upload": True,
            "rendering": True,
            "transcription": _ai(s.ai_configured),
            "ai_clip_discovery": _ai(s.ai_configured),
            "captions": _ai(s.ai_configured),
            "billing": {"available": False, "reason": "Stripe checkout is planned for phase 3."},
            "email": {"available": False, "reason": "Transactional email is planned for phase 3."},
            "url_import": {
                "available": False,
                "reason": "Direct upload is the supported input method.",
            },
            "social_publishing": {"available": False, "reason": "Planned for phase 4."},
        },
    }
