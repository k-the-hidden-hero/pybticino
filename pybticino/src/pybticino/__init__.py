"""Python library for interacting with the BTicino/Netatmo API."""

# Import main classes for easier access
from .auth import AuthHandler
from .account import AsyncAccount
from .websocket import WebsocketClient
from .models import Home, Module, Event  # Expose models

# Import exceptions for easier handling
from .exceptions import PyBticinoException, AuthError, ApiError

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
