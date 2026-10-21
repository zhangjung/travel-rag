from __future__ import annotations

from travel_rag.domain.models import (
    Itinerary,
    ResearchReport,
    TravelRequest,
    ValidationIssue,
    ValidationResult,
)


def validate_itinerary(
    request: TravelRequest,
    report: ResearchReport,
    itinerary: Itinerary,
) -> ValidationResult:
    """Validate hard constraints deterministically, without using an LLM."""

    issues: list[ValidationIssue] = []
    if itinerary.destination != request.destination:
        issues.append(
            ValidationIssue(
                severity="error",
                code="DESTINATION_MISMATCH",
                message="行程目的地与用户需求不一致。",
            )
        )
    if itinerary.days != request.days or len(itinerary.schedule) != request.days:
        issues.append(
            ValidationIssue(
                severity="error",
                code="DAY_COUNT_MISMATCH",
                message=f"应生成 {request.days} 天，实际为 {len(itinerary.schedule)} 天。",
            )
        )

    actual_days = [item.day for item in itinerary.schedule]
    expected_days = list(range(1, request.days + 1))
    if actual_days != expected_days:
        issues.append(
            ValidationIssue(
                severity="error",
                code="DAY_SEQUENCE_INVALID",
                message=f"日期序号应为 {expected_days}，实际为 {actual_days}。",
            )
        )

    if itinerary.total_estimated_cost_cny > request.budget_cny:
        issues.append(
            ValidationIssue(
                severity="error",
                code="BUDGET_EXCEEDED",
                message=(
                    f"预计花费 {itinerary.total_estimated_cost_cny} 元，"
                    f"超过预算 {request.budget_cny} 元。"
                ),
            )
        )

    valid_evidence_ids = {item.evidence_id for item in report.evidence}
    for day in itinerary.schedule:
        if not all([day.morning.strip(), day.afternoon.strip(), day.evening.strip()]):
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="EMPTY_TIME_SLOT",
                    message="早、午、晚安排均不能为空。",
                    day=day.day,
                )
            )
        unknown = set(day.evidence_ids) - valid_evidence_ids
        if unknown:
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="UNKNOWN_EVIDENCE",
                    message=f"引用了不存在的证据：{sorted(unknown)}。",
                    day=day.day,
                )
            )
        if not day.evidence_ids:
            issues.append(
                ValidationIssue(
                    severity="warning",
                    code="MISSING_EVIDENCE",
                    message="该日安排没有引用调研证据。",
                    day=day.day,
                )
            )

    return ValidationResult(
        passed=not any(issue.severity == "error" for issue in issues),
        issues=issues,
    )
