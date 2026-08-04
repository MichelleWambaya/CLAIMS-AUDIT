from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import auth, sessions, flags, saved_views, reports, admin, upload, link_sync

app = FastAPI(
    title="AAR Claims Forensic Audit Platform API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to the deployed frontend origin in production
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(sessions.router)
app.include_router(flags.router)
app.include_router(saved_views.router)
app.include_router(reports.router)
app.include_router(admin.router)
app.include_router(upload.router)
app.include_router(link_sync.router)


@app.get("/health")
def health():
    return {"status": "ok"}
