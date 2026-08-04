"""Explicit errors for Candidate-scoped Snapshot lineage."""

class SnapshotSubjectError(ValueError): pass
class SnapshotCandidateSubjectMismatchError(SnapshotSubjectError): pass
class SnapshotOpportunityBindingMismatchError(SnapshotSubjectError): pass
class SnapshotMarketIdentityMismatchError(SnapshotSubjectError): pass
class SnapshotChainIncompleteError(SnapshotSubjectError): pass
class SnapshotChainReferenceConflictError(SnapshotSubjectError): pass
class UnsupportedSnapshotSubjectVersionError(SnapshotSubjectError): pass
class MalformedSnapshotSubjectError(SnapshotSubjectError): pass

__all__ = [name for name in globals() if name.startswith("Snapshot") or name.startswith("UnsupportedSnapshot") or name.startswith("MalformedSnapshot")]
