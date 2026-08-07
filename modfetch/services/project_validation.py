"""向后兼容 shim — 远程校验已迁入 modfetch.application.validation"""

from modfetch.application.validation import (  # noqa: F401
    ConfigValidationResult,
    ProjectValidationService,
    ValidationIssue,
    ValidationSuggestion,
    ensure_remote_config_valid,
    format_validation_issues,
    validation_issue_to_dict,
)
from modfetch.adapters.modrinth.facets import build_modrinth_facets  # noqa: F401

__all__ = [
    "ConfigValidationResult",
    "ProjectValidationService",
    "ValidationIssue",
    "ValidationSuggestion",
    "ensure_remote_config_valid",
    "format_validation_issues",
    "validation_issue_to_dict",
    "build_modrinth_facets",
]
