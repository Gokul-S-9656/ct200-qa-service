"""
Domain exception hierarchy.

Why this exists: without it, a failure three layers down (say, Groq
returning malformed JSON) either propagates as a raw, unhandled exception
(FastAPI turns that into an opaque 500 with no useful detail) or forces
every router to know the internals of every layer it calls in order to
catch the right thing and pick the right status code.

Instead, lower layers (llm.py, ingest.py, crud.py) raise one of these
typed, narrow exceptions. `main.py` registers exactly one handler per
type, so the mapping from "what went wrong" to "what the client sees" is
defined once, consistently, in one place -- not re-decided ad hoc in
every route function.
"""


class AppError(Exception):
    """Base class for all domain errors this service raises on purpose."""

    status_code: int = 500
    default_message: str = "An unexpected error occurred."

    def __init__(self, message: str | None = None):
        super().__init__(message or self.default_message)


class NotFoundError(AppError):
    """A requested resource (node, selection, generation) does not exist."""

    status_code = 404
    default_message = "Resource not found."


class ValidationError(AppError):
    """Client input was well-formed JSON/HTTP but semantically invalid
    (e.g. selection referencing node IDs that don't exist)."""

    status_code = 400
    default_message = "Invalid request."


class PayloadTooLargeError(AppError):
    """Uploaded content exceeds the configured size limit."""

    status_code = 413
    default_message = "Uploaded file is too large."


class LLMUnavailableError(AppError):
    """The LLM provider could not be reached at all (network/timeout/DNS).

    Distinguished from LLMResponseError because the client-facing meaning
    is different: this one is very likely transient and worth retrying
    later; a malformed response is not something retrying will fix.
    """

    status_code = 502
    default_message = "The AI provider is temporarily unavailable. Please try again shortly."


class LLMResponseError(AppError):
    """The LLM provider responded, but the response couldn't be used
    (non-2xx status, or 2xx with content that didn't parse as the
    expected JSON array shape)."""

    status_code = 502
    default_message = "The AI provider returned an unusable response."
