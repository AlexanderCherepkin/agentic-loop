# FastAPI + React Starter

Full-stack skeleton: Python/FastAPI backend and React/Vite frontend.

## Quick start

```bash
# Backend
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend (new terminal)
cd frontend
npm install
npm run dev -- --port 5173
```

## Environment

Copy `backend/.env.example` to `backend/.env` and set `DATABASE_URL` and `SECRET_KEY`.
