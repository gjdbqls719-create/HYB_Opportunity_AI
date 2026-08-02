from app.domain.market_intelligence import HumanVerification, OCRCandidate

ExternalSignalLedgerFact = OCRCandidate | HumanVerification

__all__ = ["ExternalSignalLedgerFact"]
