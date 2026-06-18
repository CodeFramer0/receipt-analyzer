from fastapi import FastAPI

from app.presentation.routes import router


def create_app() -> FastAPI:
    app = FastAPI(title="Receipt Fraud Analyzer", version="0.1.0")
    app.include_router(router)
    return app


app = create_app()
