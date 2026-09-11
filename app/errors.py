from __future__ import annotations


class AutomationError(Exception):
    code = "AUTOMATION_ERROR"


class PolicyViolation(AutomationError):
    code = "POLICY_VIOLATION"


class TargetNotFound(AutomationError):
    code = "TARGET_NOT_FOUND"


class AmbiguousTarget(AutomationError):
    code = "AMBIGUOUS_TARGET"


class CheckpointFailed(AutomationError):
    code = "CHECKPOINT_FAILED"


class PermissionDenied(AutomationError):
    code = "PERMISSION_DENIED"


class SessionExpired(AutomationError):
    code = "SESSION_EXPIRED"


class NavigationFailure(AutomationError):
    code = "NAVIGATION_FAILURE"


class StepTimeout(AutomationError):
    code = "STEP_TIMEOUT"


class SurfaceFailure(AutomationError):
    code = "SURFACE_FAILURE"


class HumanInterventionRequired(AutomationError):
    code = "HUMAN_INTERVENTION_REQUIRED"
