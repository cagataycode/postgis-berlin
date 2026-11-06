from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.db import check_db
from app.routers import analyses, layers, sql, tags

app = FastAPI(title="Berlin Amenities Map API", version="0.4.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(layers.router)
app.include_router(analyses.router)
app.include_router(tags.router)
app.include_router(sql.router)


@app.get("/health", response_model=None)
def health() -> dict[str, Any] | JSONResponse:
    try:
        return {"status": "ok", **check_db()}
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=503, content={"status": "degraded", "error": str(exc)})
