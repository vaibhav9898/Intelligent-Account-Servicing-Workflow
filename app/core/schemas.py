from typing import Optional

from pydantic import BaseModel, Field


class IntakeRequest(BaseModel):
    customer_id: str = Field(min_length=1)
    old_name: str = Field(min_length=1)
    new_name: str = Field(min_length=1)


class CheckerDecision(BaseModel):
    decision: str
    comment: Optional[str] = None
