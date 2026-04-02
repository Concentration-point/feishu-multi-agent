from dataclasses import dataclass
from enum import Enum
from typing import Optional


class AccountStatus(str, Enum):
    FRESH = "fresh"
    ACTIVE = "active"
    LIMITED = "limited"
    COOLING = "cooling"
    CHALLENGED = "challenged"
    DEAD = "dead"


@dataclass
class Account:
    id: str
    label: str
    provider: str
    region: Optional[str]
    status: str
    priority: int
    auth_file: Optional[str]
    cookie_file: Optional[str]
    created_at: str
    last_checked_at: Optional[str] = None
    last_success_at: Optional[str] = None
    last_failure_at: Optional[str] = None
    failure_count: int = 0
    cooldown_until: Optional[str] = None
    notes: Optional[str] = None
