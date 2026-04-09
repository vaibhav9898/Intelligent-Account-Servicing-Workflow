from pathlib import Path
from secrets import token_hex

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from sqlalchemy.orm import Session

from app.core.config import BASE_DIR, UPLOAD_DIR
from app.core.db import Base, engine, get_db
from app.core.models import PendingRequest
from app.core.services import mock_rps_write, write_audit
from app.core.workflow import build_workflow

app = FastAPI(title="IASW Prototype")
app.mount("/static", StaticFiles(directory=BASE_DIR / "app" / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))
workflow = build_workflow()
Base.metadata.create_all(bind=engine)


@app.get("/")
def get_intake_page(request: Request):
    return templates.TemplateResponse("intake.html", {"request": request})


@app.post("/intake")
async def intake(
    customer_id: str = Form(...),
    old_name: str = Form(...),
    new_name: str = Form(...),
    document: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    request_id = f"REQ-{token_hex(5).upper()}"
    correlation_id = f"CORR-{token_hex(5).upper()}"

    safe_name = document.filename.replace(" ", "_")
    stored_filename = f"{request_id}-{safe_name}"
    upload_path = UPLOAD_DIR / stored_filename

    payload = await document.read()
    upload_path.write_bytes(payload)

    write_audit(
        "intake_received",
        correlation_id,
        {
            "request_id": request_id,
            "customer_id": customer_id,
            "filename": stored_filename,
        },
    )

    state = {
        "request_id": request_id,
        "correlation_id": correlation_id,
        "customer_id": customer_id,
        "old_name_requested": old_name,
        "new_name_requested": new_name,
        "upload_path": Path(upload_path),
    }
    final_state = workflow.invoke(state)

    row = PendingRequest(
        request_id=request_id,
        correlation_id=correlation_id,
        customer_id=customer_id,
        change_type="LEGAL_NAME_CHANGE",
        old_name_requested=old_name,
        new_name_requested=new_name,
        old_name_extracted=final_state.get("old_name_extracted"),
        new_name_extracted=final_state.get("new_name_extracted"),
        confidence_old_name=final_state.get("confidence_old_name"),
        confidence_new_name=final_state.get("confidence_new_name"),
        confidence_authenticity=final_state.get("confidence_authenticity"),
        forgery_check=final_state.get("forgery_check"),
        recommended_action=final_state.get("recommended_action"),
        ai_summary=final_state.get("ai_summary"),
        overall_status="AI_VERIFIED_PENDING_HUMAN",
        filenet_reference_id=final_state.get("filenet_reference_id"),
    )
    db.add(row)
    db.commit()

    write_audit(
        "pending_record_created",
        correlation_id,
        {
            "request_id": request_id,
            "status": "AI_VERIFIED_PENDING_HUMAN",
        },
    )

    return RedirectResponse(url=f"/checker/{request_id}", status_code=303)


@app.get("/checker")
def checker_list(request: Request, db: Session = Depends(get_db)):
    records = db.query(PendingRequest).order_by(PendingRequest.created_at.desc()).all()
    return templates.TemplateResponse(
        "checker_list.html",
        {
            "request": request,
            "records": records,
        },
    )


@app.get("/checker/{request_id}")
def checker_detail(request_id: str, request: Request, db: Session = Depends(get_db)):
    record = db.query(PendingRequest).filter(PendingRequest.request_id == request_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Request not found")
    return templates.TemplateResponse(
        "checker_detail.html",
        {
            "request": request,
            "record": record,
        },
    )


@app.post("/checker/{request_id}/decision")
def checker_decision(
    request_id: str,
    decision: str = Form(...),
    comment: str = Form(""),
    db: Session = Depends(get_db),
):
    record = db.query(PendingRequest).filter(PendingRequest.request_id == request_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Request not found")

    if record.overall_status != "AI_VERIFIED_PENDING_HUMAN":
        raise HTTPException(status_code=400, detail="Request already finalized")

    normalized_decision = decision.strip().upper()
    if normalized_decision not in {"APPROVE", "REJECT"}:
        raise HTTPException(status_code=400, detail="Decision must be APPROVE or REJECT")

    record.checker_decision = normalized_decision
    record.checker_comment = comment or None

    if normalized_decision == "APPROVE":
        record.rps_write_reference = mock_rps_write(
            customer_id=record.customer_id,
            new_name=record.new_name_requested,
            correlation_id=record.correlation_id,
        )
        record.overall_status = "APPROVED"
    else:
        record.overall_status = "REJECTED"

    db.commit()

    write_audit(
        "checker_decision_recorded",
        record.correlation_id,
        {
            "request_id": request_id,
            "decision": normalized_decision,
            "status": record.overall_status,
            "comment": comment,
        },
    )

    return RedirectResponse(url=f"/checker/{request_id}", status_code=303)


@app.get("/api/pending/{request_id}")
def get_pending_record(request_id: str, db: Session = Depends(get_db)):
    record = db.query(PendingRequest).filter(PendingRequest.request_id == request_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Request not found")

    return {
        "request_id": record.request_id,
        "correlation_id": record.correlation_id,
        "customer_id": record.customer_id,
        "old_name_requested": record.old_name_requested,
        "new_name_requested": record.new_name_requested,
        "old_name_extracted": record.old_name_extracted,
        "new_name_extracted": record.new_name_extracted,
        "confidence_old_name": record.confidence_old_name,
        "confidence_new_name": record.confidence_new_name,
        "confidence_authenticity": record.confidence_authenticity,
        "forgery_check": record.forgery_check,
        "recommended_action": record.recommended_action,
        "ai_summary": record.ai_summary,
        "overall_status": record.overall_status,
        "filenet_reference_id": record.filenet_reference_id,
        "checker_decision": record.checker_decision,
        "checker_comment": record.checker_comment,
        "rps_write_reference": record.rps_write_reference,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }
