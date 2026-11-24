"""App errors. main.py turns them into HTTP responses; the pipeline saves them to job.json."""


class AppError(Exception):
    status_code = 400
    code = ""  # set where the client reacts to one specific error


class NotFound(AppError):
    status_code = 404


class JobNotFound(NotFound):
    pass


class JobBusy(AppError):
    status_code = 409


class CostLimitReached(AppError):
    """One more Claude call would take a job over its cost limit."""

    status_code = 409
    code = "cost_limit"


class ScriptInvalid(AppError):
    status_code = 422


class ProviderUnavailable(AppError):
    """A voice or script provider can't be used (not installed, no key, API error)."""


class StepFailed(AppError):
    status_code = 500


class UrlUnreachable(AppError):
    """A browser scene's URL didn't respond."""
