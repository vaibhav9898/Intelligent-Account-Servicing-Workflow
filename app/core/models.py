from sqlalchemy import Column, DateTime, Float, Integer, String, Text
from sqlalchemy.sql import func

from app.core.db import Base


class PendingRequest(Base):
    __tablename__ = "pending_requests"

    id = Column(Integer, primary_key=True, index=True)

    request_id = Column(String(32), unique=True, index=True, nullable=False)
    correlation_id = Column(String(32), index=True, nullable=False)
    customer_id = Column(String(64), nullable=False)
    change_type = Column(String(32), default="LEGAL_NAME_CHANGE", nullable=False)

    old_name_requested = Column(String(256), nullable=False)
    new_name_requested = Column(String(256), nullable=False)

    old_name_extracted = Column(String(256), nullable=True)
    new_name_extracted = Column(String(256), nullable=True)

    confidence_old_name = Column(Float, nullable=True)
    confidence_new_name = Column(Float, nullable=True)
    confidence_authenticity = Column(Float, nullable=True)

    forgery_check = Column(String(16), nullable=True)
    recommended_action = Column(String(16), nullable=True)

    ai_summary = Column(Text, nullable=True)
    overall_status = Column(String(64), nullable=False)

    filenet_reference_id = Column(String(64), nullable=True)
    checker_decision = Column(String(16), nullable=True)
    checker_comment = Column(Text, nullable=True)
    rps_write_reference = Column(String(64), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
