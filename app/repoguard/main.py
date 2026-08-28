from fastapi import FastAPI

app = FastAPI(
    title="RepoGuard",
    description="Evidence-backed AI repository engineering assessment",
    version="0.1.0",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy"}
