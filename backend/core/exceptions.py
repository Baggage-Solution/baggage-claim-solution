class AppError(Exception):
    def __init__(self, message: str, code: str = "APP_ERROR", status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


class UpstreamServiceError(AppError):
    def __init__(self, message: str = "Upstream service failed"):
        super().__init__(message, code="UPSTREAM_ERROR", status_code=502)


class ConfigurationError(AppError):
    def __init__(self, message: str):
        super().__init__(message, code="CONFIGURATION_ERROR", status_code=500)


class CircuitOpenError(AppError):
    def __init__(
        self, message: str = "Provider circuit is open. Please try again shortly."
    ):
        super().__init__(message, code="CIRCUIT_OPEN", status_code=503)


class ProviderNotImplementedError(RuntimeError):
    pass


class ClaimValidationError(AppError):
    def __init__(self, message: str):
        super().__init__(message, code="CLAIM_VALIDATION_ERROR", status_code=422)


class OCRConfidenceLowError(AppError):
    def __init__(
        self, message: str = "OCR confidence too low — please retake the bag tag photo."
    ):
        super().__init__(message, code="OCR_LOW_CONFIDENCE", status_code=422)
