# Solution Design and Implementation

## Executive Summary

IASW is a deterministic FastAPI + LangGraph prototype for legal name change processing with mandatory human approval before any core write action.

## Architecture

- FastAPI routes handle intake and checker decisions.
- A linear LangGraph workflow computes extraction, scores, summary, and FileNet archive reference.
- SQLite stores pending and finalized records.
- JSONL audit log captures key lifecycle events.

## HITL Boundary

- AI performs validation, extraction, scoring, summary, and staging.
- Only checker endpoint can approve/reject.
- Mock RPS write is triggered exclusively on human `APPROVE`.

## Trade-offs

- Deterministic logic improves demo repeatability.
- Synchronous workflow keeps implementation simple.
- SQLite and local filesystem mocks are suitable for prototype only.

## Hardening Roadmap

- Add OCR + LLM extraction adapters.
- Move workflow execution to async queue workers.
- Add role-based authentication and authorization.
- Replace mock RPS and FileNet with enterprise integrations.
