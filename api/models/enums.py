"""Shared enum/literal types used across schemas and validation."""

from typing import Literal

FilingStatus = Literal["single", "mfj", "mfs", "hoh", "qw"]
WorkflowStep = Literal["intake", "documents", "review", "filing", "filed"]
FormType = Literal["W-2", "1099-INT", "1098", "1099-B", "K-1", "1099-NEC", "1099-DIV", "1099-R", "1099", "Other"]
DocumentStatus = Literal["pending", "review", "approved", "verified"]
UserRole = Literal["admin", "supervisor", "preparer", "analyst"]
OrgPlan = Literal["starter", "professional", "enterprise"]
MessageRole = Literal["user", "assistant"]
MessageType = Literal["text", "document", "chart"]
ReturnSection = Literal["income", "deductions", "tax_credits", "payments"]
