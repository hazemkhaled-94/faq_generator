"""The backend's HTTP surface, and the only address the frontend holds.

Assembles the application. Wiring is in dependencies; endpoints are in
routes/.
"""

from __future__ import annotations

from fastapi import FastAPI
from starlette.middleware import Middleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from api import errors
from api.routes import ROUTERS
from settings.env import csv

app = FastAPI(
    title="qa_generator API",
    middleware=[
        Middleware(TrustedHostMiddleware, allowed_hosts=csv("API_ALLOWED_HOSTS")),
    ],
)

errors.install(app)

for router in ROUTERS:
    app.include_router(router)
