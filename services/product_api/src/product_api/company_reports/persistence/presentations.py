"""Internal immutable H1/H2 pins and CAS assignment foundation.

No router imports mutation functions from this module.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    CompanyReportPresentationAssignment, CompanyReportPresentationAssignmentJournal,
    CompanyReportPresentationPin, CompanyReportPresentationStagedPointer, CompanyReportRecord,
)


class PresentationAssignmentConflict(RuntimeError):
    code = "presentation_assignment_conflict"


async def append_presentation_pin(session: AsyncSession, *, subject_id: UUID, report: CompanyReportRecord, contract: str, generation: int) -> CompanyReportPresentationPin:
    if generation <= 0 or report.subject_id != subject_id or not report.snapshot_hash:
        raise PresentationAssignmentConflict("presentation pin identity is invalid")
    existing = await session.scalar(select(CompanyReportPresentationPin).where(
        CompanyReportPresentationPin.subject_id == subject_id,
        CompanyReportPresentationPin.presentation_contract == contract,
        CompanyReportPresentationPin.generation == generation,
    ).with_for_update())
    if existing is not None:
        if existing.report_id == report.id and existing.snapshot_hash == report.snapshot_hash:
            return existing
        raise PresentationAssignmentConflict("presentation pin generation conflicts")
    pin = CompanyReportPresentationPin(subject_id=subject_id, report_id=report.id, presentation_contract=contract, generation=generation, snapshot_hash=report.snapshot_hash)
    session.add(pin)
    await session.flush()
    return pin


async def stage_h2_pin(session: AsyncSession, *, subject_id: UUID, pin: CompanyReportPresentationPin, expected_generation: int) -> CompanyReportPresentationStagedPointer:
    if pin.subject_id != subject_id or pin.presentation_contract != "company_public_h2_v1" or expected_generation != pin.generation:
        raise PresentationAssignmentConflict("staged pointer identity is invalid")
    pointer = await session.scalar(select(CompanyReportPresentationStagedPointer).where(CompanyReportPresentationStagedPointer.subject_id == subject_id).with_for_update())
    if pointer is None:
        pointer = CompanyReportPresentationStagedPointer(subject_id=subject_id, pin_id=pin.id, expected_generation=expected_generation)
        session.add(pointer)
    elif pointer.pin_id != pin.id or pointer.expected_generation != expected_generation:
        pointer.pin_id, pointer.expected_generation = pin.id, expected_generation
    await session.flush()
    return pointer


async def assign_pin_cas(session: AsyncSession, *, subject_id: UUID, pin: CompanyReportPresentationPin, expected_generation: int) -> CompanyReportPresentationAssignment:
    if pin.subject_id != subject_id or expected_generation != pin.generation:
        raise PresentationAssignmentConflict("assignment pin identity is invalid")
    assignment = await session.scalar(select(CompanyReportPresentationAssignment).where(CompanyReportPresentationAssignment.subject_id == subject_id).with_for_update())
    if assignment is None:
        if expected_generation != 1:
            raise PresentationAssignmentConflict("assignment generation conflicts")
        assignment = CompanyReportPresentationAssignment(subject_id=subject_id, pin_id=pin.id, generation=1)
        session.add(assignment)
        await session.flush()
        session.add(CompanyReportPresentationAssignmentJournal(assignment_id=assignment.id, pin_id=pin.id, generation=1))
    elif assignment.generation != expected_generation - 1:
        raise PresentationAssignmentConflict("assignment generation conflicts")
    else:
        assignment.pin_id, assignment.generation = pin.id, expected_generation
        session.add(CompanyReportPresentationAssignmentJournal(assignment_id=assignment.id, pin_id=pin.id, generation=expected_generation))
    await session.flush()
    return assignment


__all__ = ["PresentationAssignmentConflict", "append_presentation_pin", "assign_pin_cas", "stage_h2_pin"]
