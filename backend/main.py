import os
import logging
from pathlib import Path
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from aiohttp import ClientSession
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv(Path(__file__).parent.parent / ".env")

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

from routes import router, set_state


@asynccontextmanager
async def lifespan(app: FastAPI):
    session = ClientSession()
    set_state(session, None, None)
    yield
    await session.close()


app = FastAPI(title="Alexa To-Do API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)



