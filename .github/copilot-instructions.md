# Copilot Instructions for TaskBoard

## Project Overview

TaskBoard is a task dashboard that merges Amazon Alexa TODO lists with locally-stored tasks backed by SQLite. It's deployable as a Home Assistant add-on via Docker.

## Tech Stack

- **Backend:** Python ≥ 3.12, FastAPI, SQLite — managed with `uv`
- **Frontend:** React (TypeScript), Create React App
- **Deployment:** Docker (multi-stage build), Home Assistant add-on

## Project Structure

- `task_board/backend/` — FastAPI app (`app/main.py`, `app/routes.py`, `app/helpers.py`)
- `task_board/frontend/` — React TypeScript app (`src/`)
- `task_board/Dockerfile` — Production container
- `task_board/run.sh` — Docker entrypoint
-  `task_board/backend/docs/pyalexatodo` - Contains the python package that this code is based on. See it as an example for how to use the Alexa API. It is not used in the codebase, but it is a good reference for understanding how to interact with the Alexa API.

## Development Commands

```bash
# Backend
cd task_board/backend
uv sync
.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Frontend
cd task_board/frontend
npm install
npm start
```

## Coding Conventions

- Backend uses Python type hints and FastAPI dependency injection
- Frontend uses TypeScript strict mode
- Tasks have priorities: `high`, `medium`, `low`
- API routes are grouped: `/auth/*`, `/lists/*`, `/api/*`
- Environment variables are loaded from `.env` (never commit secrets) for local development
- Environment variables are loaded from home assistant front end for production 

## Important Notes

- The `.env` file contains Amazon credentials — never commit it
- `DATABASE_PATH` is relative to `backend/` in dev, overridden to `/data/tasks.db` in Docker
- The React dev server proxies API requests to the backend on port 8000
- Production serves the React build as static files from FastAPI
