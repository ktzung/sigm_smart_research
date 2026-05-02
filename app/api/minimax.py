from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pathlib import Path
import json
from typing import Optional
from app.core.config import settings

router = APIRouter()

CONFIG_PATH = Path("storage/minimax_config.json")


class MinimaxConfigUpdate(BaseModel):
    model: Optional[str] = None
    base_url: Optional[str] = None
    persist_api_key: Optional[bool] = False
    api_key: Optional[str] = None


def _read_config():
    if not CONFIG_PATH.exists():
        return {
            "provider": "minimax",
            "model": getattr(settings, "minimax_model", None),
            "base_url": getattr(settings, "minimax_base_url", None),
            "api_key_set": bool(getattr(settings, "minimax_api_key", None)),
        }
    try:
        data = json.loads(CONFIG_PATH.read_text())
        data["api_key_set"] = data.get("api_key_set", False)
        return data
    except Exception:
        return {"provider": "minimax"}


@router.get("/config/minimax")
def get_minimax_config():
    """Return the current MiniMax configuration (does not reveal raw API key)."""
    return _read_config()


@router.post("/config/minimax")
def set_minimax_config(payload: MinimaxConfigUpdate):
    """Update non-sensitive MiniMax config and optionally mark an API key as set.

    - To set or rotate an API key, prefer setting the `MINIMAX_API_KEY` environment variable.
    - If `persist_api_key` is true and `api_key` is supplied, we will record only a masked indicator (we do NOT persist raw keys).
    """
    cfg = _read_config()
    if payload.model:
        cfg["model"] = payload.model
    if payload.base_url:
        cfg["base_url"] = payload.base_url
    if payload.persist_api_key:
        if not payload.api_key:
            raise HTTPException(400, "persist_api_key true requires api_key to be provided in request body")
        cfg["api_key_set"] = True

    try:
        CONFIG_PATH.parent.mkdir(exist_ok=True)
        # Never persist raw api_key
        tmp = {k: v for k, v in cfg.items() if k != "api_key"}
        CONFIG_PATH.write_text(json.dumps(tmp, indent=2))
    except Exception as e:
        raise HTTPException(500, f"Failed to persist minimax config: {e}")

    return {"status": "ok", "config": tmp}


@router.get("/config/minimax/health")
def minimax_health_check():
    """Perform a lightweight connectivity check using configured MiniMax base URL. This endpoint only checks reachability; it does not transmit API keys from disk."""
    import requests

    cfg = _read_config()
    base = cfg.get("base_url") or getattr(settings, "minimax_base_url", None)
    if not base:
        raise HTTPException(400, "MiniMax base URL not configured")
    try:
        url = base.rstrip("/") + "/v1/health"
        r = requests.get(url, timeout=5)
        return {"status_code": r.status_code, "ok": r.ok}
    except Exception as e:
        raise HTTPException(502, f"Health check failed: {e}")
