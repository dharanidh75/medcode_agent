# Nexora - MedCode Assist (Health Team 004)

**Tech for Good 2026** · GDG Coimbatore

**MedCode Assist** is an AI-powered medical coding assistant that automates the translation of unstructured clinical discharge summaries into accurate ICD-10 and RxNorm codes. It uses a custom NLP pipeline with FAISS vector search and Llama-3 to pre-process clinical notes, drastically reducing the manual burden on medical coders.

## Live Deployments
- **Frontend (Vercel):** `[DEPLOYMENT_URL_PENDING]`
- **Backend API (Render):** `[DEPLOYMENT_URL_PENDING]`
- **Local Model Tunnel:** `[NGROK_URL_PENDING]`

## Quick Start (Fresh Clone)

If you are a judge or developer cloning this repository for the first time, follow these precise steps to get the environment running locally.

### 1. Environment Variables
Copy the `.env.example` templates in both `src/frontend` and `src/backend`, and fill them in:
```bash
cp src/frontend/.env.example src/frontend/.env
cp src/backend/.env.example src/backend/.env
```

### 2. Generate the Local Model Index (FAISS)
Because the dense vector indexes are too large for GitHub (300MB+), we only track the raw `.txt` datasets. **You must build the FAISS `.bin` indexes locally before starting the app.**

Run the automated setup script from the root of the repository:
```bash
./setup_model.sh
```
*(Note: This creates a python virtual environment, installs dependencies, and runs `indexer.py` on the datasets. It will take ~5-15 minutes depending on your CPU).*

### 3. Start the Services
Once the model is setup, you need to run three terminals:

**Terminal 1 (Local Model Service):**
```bash
cd src/local_model
source .venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8001
```

**Terminal 2 (Backend API):**
```bash
cd src/backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

**Terminal 3 (Frontend UI):**
```bash
cd src/frontend
npm install
npm run dev
```

## Architecture
- **Frontend:** React + Vite (Lucide icons)
- **Backend API:** FastAPI + Supabase (Database/Realtime)
- **Local Model:** FAISS + SentenceTransformers + BM25 + Groq Llama-3 (running locally to protect PHI/PII data routing)
