from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Callable

from app.application.sourcing.models import (
    AdmitFounderSourcingCommand,
    DomesticSellingProductLineageReference,
    NewToMarketDomesticSellingProductLineageReference,
    ReviseFounderSourcingQuoteCommand,
    SourcingAdmissionNotFoundError,
    SourcingAdmissionReceipt,
    SourcingAdmissionResult,
    SourcingAuthorityError,
    SourcingIdentityGenerationError,
    SourcingProductMatchNotVerifiedError,
    SourcingQuoteRevisionConflictError,
)
from app.application.sourcing.ports import SourcingAuthorityRepository
from app.domain.sourcing import (
    DOMESTIC_SELLING_SOURCING_AUTHORITY_SCHEMA_VERSION,
    NEW_TO_MARKET_DOMESTIC_SELLING_SOURCING_AUTHORITY_SCHEMA_VERSION,
    SOURCING_AUTHORITY_SCHEMA_VERSION,
    DomesticSellingProductLineage,
    FounderSourcingAdmission,
    MatchVerificationStatus,
    NewToMarketDomesticSellingProductLineage,
    ProductMatchVerification,
    SourcingProductIdentity,
    SupplierIdentity,
    SupplierQuoteRevision,
)


class SourcingDomesticSellingLineageError(SourcingAuthorityError):
    pass


def _generated(generator: Callable[[], str], name: str) -> str:
    try:
        value = generator()
    except Exception:
        raise
    if not isinstance(value, str) or not value.strip():
        raise SourcingIdentityGenerationError(f"{name} generator returned invalid identity")
    return value.strip()


def _time(clock: Callable[[], datetime], name: str) -> datetime:
    value = clock()
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


class AdmitFounderSourcing:
    """Issues authoritative identities only after persisted replay is ruled out."""

    def __init__(
        self,
        repository: SourcingAuthorityRepository,
        *,
        supplier_id_generator: Callable[[], str],
        sourcing_product_id_generator: Callable[[], str],
        quote_id_generator: Callable[[], str],
        match_verification_id_generator: Callable[[], str],
        admission_id_generator: Callable[[], str],
        admission_clock: Callable[[], datetime],
        committed_clock: Callable[[], datetime],
    ) -> None:
        generators = (
            supplier_id_generator, sourcing_product_id_generator, quote_id_generator,
            match_verification_id_generator, admission_id_generator,
            admission_clock, committed_clock,
        )
        if any(not callable(value) for value in generators):
            raise TypeError("identity generators and clock must be callable")
        self._repository = repository
        self._supplier_id = supplier_id_generator
        self._product_id = sourcing_product_id_generator
        self._quote_id = quote_id_generator
        self._verification_id = match_verification_id_generator
        self._admission_id = admission_id_generator
        self._admission_clock = admission_clock
        self._committed_clock = committed_clock

    def execute(self, command: AdmitFounderSourcingCommand) -> SourcingAdmissionResult:
        if not isinstance(command, AdmitFounderSourcingCommand):
            raise TypeError("command must be AdmitFounderSourcingCommand")
        replay = self._repository.validate_replay(command.command_id, command.fingerprint)
        if replay is not None:
            return replace(replay, replayed=True)
        if command.match_status is not MatchVerificationStatus.VERIFIED_MATCH:
            raise SourcingProductMatchNotVerifiedError(
                "Sourcing admission requires a verified match"
            )
        lineage = self._resolve_lineage(command.selling_product_lineage)
        supplier_id = _generated(self._supplier_id, "supplier_id")
        product_id = _generated(self._product_id, "sourcing_product_id")
        quote_id = _generated(self._quote_id, "quote_id")
        verification_id = _generated(self._verification_id, "verification_id")
        admission_id = _generated(self._admission_id, "admission_id")
        supplier = SupplierIdentity(
            supplier_id, command.supplier_platform,
            command.external_supplier_reference, command.supplier_display_name,
        )
        product = SourcingProductIdentity(
            product_id, supplier_id, command.external_product_reference,
            command.option_reference, command.sku_reference, command.source_url,
            command.product_observed_at,
        )
        quote = SupplierQuoteRevision(
            quote_id, 1, product_id, command.quoted_unit_price,
            command.minimum_order_quantity, command.quoted_quantity,
            command.shipping_terms, command.lead_time_availability,
            command.lead_time_days, command.quote_observed_at,
            command.quote_valid_until, command.quote_evidence,
        )
        verification = ProductMatchVerification(
            verification_id, lineage, product_id,
            command.match_status, command.operator_id, command.verified_at,
            command.match_evidence, command.proposal_score, command.proposal_version,
        )
        admission = FounderSourcingAdmission(
            admission_id, 1, lineage, supplier, product,
            quote, verification, command.operator_id, command.requested_at,
            _time(self._admission_clock, "admitted_at"),
            self._admission_schema_version(lineage),
        )
        receipt = SourcingAdmissionReceipt(
            command.command_id, admission_id, 1, command.fingerprint,
            _time(self._committed_clock, "committed_at"),
        )
        return self._repository.save_admission(command, admission, receipt)

    def _resolve_lineage(self, lineage):
        if isinstance(lineage, DomesticSellingProductLineageReference):
            source = self._repository.get_domestic_selling_admission(
                lineage.domestic_selling_admission_id
            )
            if source is None:
                raise SourcingAdmissionNotFoundError(
                    "domestic selling Opportunity admission was not found"
                )
            return DomesticSellingProductLineage(
                opportunity_identity=source.domestic_opportunity_identity,
                domestic_selling_admission_id=source.admission_id,
                source_opportunity_identity=source.source_opportunity_identity,
                source_product_observation_snapshot_id=source.source_product_snapshot_id,
                market_observation_identity=source.domestic_market_identity,
                product_equivalence_evidence_reference=(
                    source.product_equivalence.evidence_reference
                ),
            )
        if isinstance(
            lineage,
            NewToMarketDomesticSellingProductLineageReference,
        ):
            source = self._repository.get_new_to_market_domestic_selling_admission(
                lineage.new_to_market_domestic_selling_admission_id
            )
            if source is None:
                raise SourcingAdmissionNotFoundError(
                    "new-to-market domestic selling Opportunity admission was not found"
                )
            return NewToMarketDomesticSellingProductLineage(
                opportunity_identity=source.domestic_opportunity_identity,
                new_to_market_domestic_selling_admission_id=source.admission_id,
                target_identity=source.target_identity,
            )
        self._validate_domestic_lineage(lineage)
        self._validate_new_to_market_lineage(lineage)
        return lineage

    @staticmethod
    def _admission_schema_version(lineage) -> str:
        if isinstance(lineage, DomesticSellingProductLineage):
            return DOMESTIC_SELLING_SOURCING_AUTHORITY_SCHEMA_VERSION
        if isinstance(lineage, NewToMarketDomesticSellingProductLineage):
            return NEW_TO_MARKET_DOMESTIC_SELLING_SOURCING_AUTHORITY_SCHEMA_VERSION
        return SOURCING_AUTHORITY_SCHEMA_VERSION

    def _validate_domestic_lineage(self, lineage) -> None:
        if not isinstance(lineage, DomesticSellingProductLineage):
            return
        source = self._repository.get_domestic_selling_admission(
            lineage.domestic_selling_admission_id
        )
        if source is None or (
            source.domestic_opportunity_identity != lineage.opportunity_identity
            or source.source_opportunity_identity != lineage.source_opportunity_identity
            or source.source_product_snapshot_id
            != lineage.source_product_observation_snapshot_id
            or source.domestic_market_identity != lineage.market_observation_identity
            or source.product_equivalence.evidence_reference
            != lineage.product_equivalence_evidence_reference
        ):
            raise SourcingDomesticSellingLineageError(
                "domestic selling Opportunity lineage differs from persisted admission"
            )

    def _validate_new_to_market_lineage(self, lineage) -> None:
        if not isinstance(lineage, NewToMarketDomesticSellingProductLineage):
            return
        source = self._repository.get_new_to_market_domestic_selling_admission(
            lineage.new_to_market_domestic_selling_admission_id
        )
        if source is None or (
            source.domestic_opportunity_identity != lineage.opportunity_identity
            or source.target_identity != lineage.target_identity
        ):
            raise SourcingDomesticSellingLineageError(
                "new-to-market domestic selling Opportunity lineage differs from "
                "persisted admission"
            )


class ReviseFounderSourcingQuote:
    """Appends a quote revision while retaining admission and quote identity."""

    def __init__(
        self,
        repository: SourcingAuthorityRepository,
        *,
        admission_clock: Callable[[], datetime],
        committed_clock: Callable[[], datetime],
    ) -> None:
        if not callable(admission_clock) or not callable(committed_clock):
            raise TypeError("admission and committed clocks must be callable")
        self._repository = repository
        self._admission_clock = admission_clock
        self._committed_clock = committed_clock

    def execute(self, command: ReviseFounderSourcingQuoteCommand) -> SourcingAdmissionResult:
        if not isinstance(command, ReviseFounderSourcingQuoteCommand):
            raise TypeError("command must be ReviseFounderSourcingQuoteCommand")
        replay = self._repository.validate_replay(command.command_id, command.fingerprint)
        if replay is not None:
            return replace(replay, replayed=True)
        current = self._repository.get_admission(command.admission_id)
        if current is None:
            raise SourcingAdmissionNotFoundError("Sourcing admission was not found")
        if current.revision != command.expected_revision:
            raise SourcingQuoteRevisionConflictError(
                "Sourcing admission revision conflicts with expected revision"
            )
        revision = current.revision + 1
        quote = SupplierQuoteRevision(
            current.quote_revision.quote_id, revision,
            current.sourcing_product_identity.sourcing_product_id,
            command.quoted_unit_price, command.minimum_order_quantity,
            command.quoted_quantity, command.shipping_terms,
            command.lead_time_availability, command.lead_time_days,
            command.quote_observed_at, command.quote_valid_until,
            command.quote_evidence,
        )
        admission = FounderSourcingAdmission(
            current.admission_id, revision, current.selling_product_lineage,
            current.supplier_identity, current.sourcing_product_identity, quote,
            current.match_verification, command.operator_id, command.requested_at,
            _time(self._admission_clock, "admitted_at"), current.schema_version,
        )
        receipt = SourcingAdmissionReceipt(
            command.command_id, admission.admission_id, revision,
            command.fingerprint, _time(self._committed_clock, "committed_at"),
        )
        return self._repository.save_quote_revision(command, admission, receipt)
