from fastapi import APIRouter, Depends, HTTPException
from typing import List

from ..config import Config
from ..logging_config import setup_logger

logger = setup_logger(__name__)
router = APIRouter(prefix="/config", tags=["config"])

# Assuming config is a singleton or easily accessible
# If not, you might need to use Depends or app state
config = Config()

@router.get("/ignored-domains")
async def get_ignored_domains():
    """Get list of ignored domain patterns"""
    try:
        return {"ignored_domains": config.config.get('ignored_domains', [])}
    except Exception as e:
        logger.error(f"Error getting ignored domains: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve ignored domains")


@router.post("/ignored-domains")
async def add_ignored_domain(pattern: str):
    """Add a new domain pattern to ignored list"""
    try:
        config.add_ignored_domain(pattern)
        return {"status": "success", "message": f"Added pattern: {pattern}"}
    except Exception as e:
        logger.error(f"Error adding ignored domain '{pattern}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to add ignored domain")


@router.delete("/ignored-domains/{pattern}")
async def remove_ignored_domain(pattern: str):
    """Remove a domain pattern from ignored list"""
    try:
        config.remove_ignored_domain(pattern)
        return {"status": "success", "message": f"Removed pattern: {pattern}"}
    except Exception as e:
        logger.error(f"Error removing ignored domain '{pattern}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to remove ignored domain")