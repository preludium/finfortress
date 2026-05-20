import json
import sys
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

router = APIRouter()
MANIFEST_PATH = ROOT / "data" / "sources_manifest.json"


@router.get("/sources")
async def sources():
    if not MANIFEST_PATH.exists():
        return JSONResponse([])
    with MANIFEST_PATH.open("r", encoding="utf-8") as fh:
        return JSONResponse(json.load(fh))
