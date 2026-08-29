from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from repoguard.api.routes import router

app = FastAPI(
    title="RepoGuard",
    description="Evidence-backed AI repository engineering assessment",
    version="0.1.0",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy"}


app.include_router(router)

app.mount(
    "/",
    StaticFiles(directory=Path(__file__).parent / "static", html=True),
    name="static",
)
