"""Python library for interacting with the BTicino/Netatmo API."""

# Import main classes for easier access
from .account import AsyncAccount
from .auth import AuthHandler

# Import exceptions for easier handling
from .exceptions import ApiError, AuthError, PyBticinoException
from .models import Event, Home, Module  # Expose models
from .websocket import WebsocketClient

# Define package version (consider using importlib.metadata in the future)
__version__ = "0.1.0"  # Update version to reflect refactoring

# Define what gets imported with 'from pybticino import *'
__all__ = [
    "AuthHandler",
    "AsyncAccount",
    "WebsocketClient",
    "Home",
    "Module",
    "Event",
    "PyBticinoException",
    "AuthError",
    "ApiError",
    "__version__",
]
