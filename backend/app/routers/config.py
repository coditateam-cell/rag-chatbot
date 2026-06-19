"""
config.py — FastAPI router for config manager hot-reload endpoint.
"""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.routers.deps import get_config_manager

router = APIRouter(prefix="/config", tags=["config"])


@router.post("/reload")
async def reload_config(config_manager = Depends(get_config_manager)):
    """Triggers hot-reload of JSON/YAML config files."""
    result = config_manager.reload()
    if result.success:
        return {"status": "success", "detail": "Configuration reloaded successfully."}
    else:
        return JSONResponse(
            status_code=400,
            content={
                "error": "invalid_configuration",
                "detail": f"Configuration validation failed for parameter '{result.parameter}': {result.error}",
            },
        )
