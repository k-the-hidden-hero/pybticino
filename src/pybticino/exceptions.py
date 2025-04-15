"""Custom exceptions for pybticino."""


class PyBticinoException(Exception):
    """Base class for pybticino exceptions."""


class AuthError(PyBticinoException):
    """Raised when authentication fails."""


class ApiError(PyBticinoException):
    """Raised when an API call fails."""

    def __init__(self, status_code: int, error_message: str) -> None:
        """Initialize the API error."""
        self.status_code = status_code
        self.error_message = error_message
        super().__init__(f"API Error {status_code}: {error_message}")
