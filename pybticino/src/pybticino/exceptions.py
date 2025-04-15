"""Custom exceptions for pybticino."""


class PyBticinoException(Exception):
    """Base class for pybticino exceptions."""

    pass


class AuthError(PyBticinoException):
    """Raised when authentication fails."""

    pass


class ApiError(PyBticinoException):
    """Raised when an API call fails."""

    def __init__(self, status_code, error_message):
        self.status_code = status_code
        self.error_message = error_message
        super().__init__(f"API Error {status_code}: {error_message}")
