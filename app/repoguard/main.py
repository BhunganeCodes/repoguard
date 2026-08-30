import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from repoguard.api.routes import router

logger = logging.getLogger("repoguard")

app = FastAPI(
    title="RepoGuard",
    description="Evidence-backed AI repository engineering assessment",
    version="0.1.0",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.exception_handler(Exception)
async def _unhandled_error(_request: Request, exc: Exception) -> JSONResponse:
    """Last-resort guard so an unexpected error never leaks a traceback.

    Expected failures are already handled at the product boundary; this exists
    only to keep the public surface safe: a JSON body with a stable code, no
    Python internals, no filesystem paths, and no stack trace.
    """
    logger.exception("unhandled error during product request: %s", exc)
    return JSONResponse(
        status_code=500,
        content={
            "detail": {
                "error": "internal_error",
                "message": "The assessment service hit an unexpected error.",
            }
        },
    )


app.include_router(router)

app.mount(
    "/",
    StaticFiles(directory=Path(__file__).parent / "static", html=True),
    name="static",
)
