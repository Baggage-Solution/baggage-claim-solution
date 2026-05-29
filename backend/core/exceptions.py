class AppError(Exception):
    """Base application exception carrying an error code and HTTP status code.

    All domain errors should subclass AppError rather than raising generic
    Exception or HTTPException so error handling stays consistent.
    """

    def __init__(self, message: str, code: str = "APP_ERROR", status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


class UpstreamServiceError(AppError):
    """Raised when an external API (Gemini, Supabase) returns a non-2xx response."""

    def __init__(self, message: str = "Upstream service failed"):
        super().__init__(message, code="UPSTREAM_ERROR", status_code=502)


class ConfigurationError(AppError):
    """Raised when a required environment variable or configuration is missing."""

    def __init__(self, message: str):
        super().__init__(message, code="CONFIGURATION_ERROR", status_code=500)


class CircuitOpenError(AppError):
    """Raised by provider circuit breakers when too many upstream failures occur."""

    def __init__(
        self, message: str = "Provider circuit is open. Please try again shortly."
    ):
        super().__init__(message, code="CIRCUIT_OPEN", status_code=503)


class ProviderNotImplementedError(RuntimeError):
    """Raised when a provider abstract method is called without a concrete implementation."""

    pass


class ClaimValidationError(AppError):
    """Raised when a claim submission fails validation (e.g. missing photos or fields)."""

    def __init__(self, message: str):
        super().__init__(message, code="CLAIM_VALIDATION_ERROR", status_code=422)


class OCRConfidenceLowError(AppError):
    """Raised when OCR confidence falls below the acceptable threshold."""

    def __init__(
        self, message: str = "OCR confidence too low — please retake the bag tag photo."
    ):
        super().__init__(message, code="OCR_LOW_CONFIDENCE", status_code=422)
