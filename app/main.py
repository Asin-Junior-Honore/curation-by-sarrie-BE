from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from .config import settings
from .database import connect_to_mongo, close_mongo_connection
from .services.auth import seed_super_admin
from .routers import products, admin, checkout, auth, users, orders


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_to_mongo()
    await seed_super_admin()
    yield
    await close_mongo_connection()


app = FastAPI(
    title="Curation by Sarrie — Backend",
    version="0.3.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router)
app.include_router(products.router)
app.include_router(admin.router)
app.include_router(users.router)
app.include_router(checkout.router)
app.include_router(orders.router)


@app.get("/")
async def root():
    return {
        "name": "Curation by Sarrie API",
        "status": "running",
        "version": "0.3.0",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}