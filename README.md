# Pip - English buddy for children under 7

Chatbot that teaches English in 3 levels, switches between learning / conversation / engagement / support modes,
teaches social-emotional skills, remembers each child's progress, and answers in ~milliseconds.

- Design doc: [DESIGN.md](DESIGN.md)  |  Architecture diagram: [docs/architecture.svg](docs/architecture.svg)

## Run locally
```bash
pip install -r requirements.txt
uvicorn app.main:app --reload          # open http://127.0.0.1:8000
python -m unittest discover -s tests -t .   # 19 tests, stdlib only
```

## Deploy (live URL)
Docker-based hosts (Render, Railway, Fly.io, Cloud Run): point at this repo, it uses the `Dockerfile`.
Without Docker: build `pip install -r requirements.txt`, start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
Health check: `/health`. Optional env vars: see `.env.example` (`ANTHROPIC_API_KEY` enables LLM-flavoured free chat; `DATA_DIR` persists progress).
Use an always-on instance (not a sleeping free tier) to keep first-response latency under 2 s.

## Layout
```
app/models.py      data models (Profile, Exercise, Reply, Mode)
app/curriculum.py  L1-L3 content, exercise generation, answer checking, level rules
app/detect.py      emotion + safety detection, child-mode detection
app/engine.py      dialog engine and the four mode handlers (incl. SEL)
app/llm.py         optional LLM for free chat only (1 s timeout, fallback)
app/store.py       profile store (memory + JSON, swap for Redis)
app/main.py        FastAPI: /api/chat, /health, static UI
static/index.html  kid-friendly UI (tap buttons, text-to-speech, mic)
tests/             unit tests
```
