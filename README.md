# IASW Prototype

Intelligent Account Servicing Workflow (IASW) prototype demonstrating a digital Maker + mandatory human Checker flow for legal name change requests.

## Stack

- FastAPI
- LangGraph
- SQLAlchemy (SQLite)
- Jinja2 templates

## Quick Start

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Run the server:

```bash
uvicorn app.main:app --reload
```

3. Open:

- http://127.0.0.1:8000/

## Demo

1. Submit the intake form with a file (try `samples/marriage_certificate_demo.txt`).
2. Open checker queue and request detail.
3. Approve or reject.

## Important HITL Rule

AI can prepare and stage records but cannot finalize updates. Only the checker decision endpoint can execute mock RPS write on `APPROVE`.
