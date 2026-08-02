from app.domain.market_intelligence import OCRCandidate, OCRResult

OCRExtractionOutput = OCRResult
OCRCandidateBatch = tuple[OCRCandidate, ...]

__all__ = ["OCRCandidateBatch", "OCRExtractionOutput"]
