import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.background.tasks import run_overdue_tasks_worker
from app.core.config import settings
from app.routers.auth import router as auth_router
from app.routers.comments import router as comments_router
from app.routers.tasks import router as tasks_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: запуск періодичного воркера
    worker_task = asyncio.create_task(run_overdue_tasks_worker())
    yield
    # Shutdown: коректна зупинка воркера (graceful shutdown)
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title=settings.PROJECT_NAME,
    lifespan=lifespan,
)

app.include_router(auth_router)
app.include_router(tasks_router)
app.include_router(comments_router)


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok"}
