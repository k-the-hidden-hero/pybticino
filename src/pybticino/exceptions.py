"""Custom exceptions for pybticino."""


class PyBticinoException(Exception):
    """Base exception for all errors raised by the pybticino library.

    All other library-specific exceptions inherit from this class.
    """


class AuthError(PyBticinoException):
    """Raised when authentication with the BTicino/Netatmo API fails.

    This can occur due to invalid credentials, network issues during the
    authentication process, or problems refreshing the access token.
    """


class ApiError(PyBticinoException):
    """Raised when a BTicino/Netatmo API call returns an error status.

    Attributes:
        status_code (int): The HTTP status code returned by the API.
        error_message (str): The error message provided by the API or a
                             description of the error.

    """

    def __init__(self, status_code: int, error_message: str) -> None:
        """Initialize the API error.

        Args:
            status_code (int): The HTTP status code from the API response.
            error_message (str): The error message associated with the failure.

        """
        self.status_code = status_code
        self.error_message = error_message
        super().__init__(f"API Error {status_code}: {error_message}")
