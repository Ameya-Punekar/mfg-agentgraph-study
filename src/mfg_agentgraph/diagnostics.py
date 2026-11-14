"""Allow-listed diagnostics for unexpected fail-closed boundary errors."""

from __future__ import annotations

import logging
from enum import StrEnum
from typing import Final

LOGGER_NAME = "mfg_agentgraph.diagnostics"
_LOGGER = logging.getLogger(LOGGER_NAME)
_ERROR_MESSAGE: Final = "MFG-AgentGraph operation failed"


class DiagnosticCode(StrEnum):
    """Stable codes for unexpected errors hidden by fail-closed boundaries."""

    SHACL_VALIDATION_ENGINE_ERROR = "shacl_validation_engine_error"
    BOUNDED_REPAIR_ATTEMPT_ERROR = "bounded_repair_attempt_error"


class DiagnosticComponent(StrEnum):
    """Components allowed to emit a sanitized diagnostic."""

    SHACL_VALIDATION = "shacl_validation"
    BOUNDED_REPAIR = "bounded_repair"


class DiagnosticOperation(StrEnum):
    """Operations allowed to emit a sanitized diagnostic."""

    VALIDATE_RECOMMENDED_ACTION = "validate_recommended_action"
    REPAIR_ATTEMPT = "repair_attempt"


def emit_diagnostic(
    *,
    diagnostic_code: DiagnosticCode,
    component: DiagnosticComponent,
    operation: DiagnosticOperation,
    run_id: str,
    attempt_index: int | None = None,
) -> None:
    """Emit stable metadata without accepting exception or payload content."""

    extra: dict[str, str | int] = {
        "diagnostic_code": diagnostic_code.value,
        "component": component.value,
        "operation": operation.value,
        "run_id": run_id,
    }
    if attempt_index is not None:
        extra["attempt_index"] = attempt_index
    try:
        _LOGGER.error(_ERROR_MESSAGE, extra=extra)
    except Exception:
        return
