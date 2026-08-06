"""Production identity supplier for authoritative OCR Candidates."""

from __future__ import annotations

from uuid import uuid4


class ProductionOCRCandidateIdentityGenerator:
    """Supplies one server-owned opaque OCR Candidate identity per call."""

    __slots__ = ()

    def __call__(self) -> str:
        return uuid4().hex


__all__ = ["ProductionOCRCandidateIdentityGenerator"]
