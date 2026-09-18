from pydantic import BaseModel
from typing import Optional


class Commitment(BaseModel):
    action: str
    owner: Optional[str] = None
    related_person: Optional[str] = None
    deadline: Optional[str] = None  # ISO date as string
    status: Optional[str] = None
    source: Optional[str] = None
    evidence: Optional[str] = None

    class Config:
        schema_extra = {
            "example": {
                "action": "Send updated vendor list to Raghav",
                "owner": "Arjun Malhotra",
                "related_person": "Raghav Sethi",
                "deadline": "2026-09-23",
                "status": "overdue",
                "source": "email",
                "evidence": "will send by tomorrow (Wednesday) morning for sure",
            }
        }
