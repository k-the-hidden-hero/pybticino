"""Data models for pybticino."""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

# Placeholder models - To be refined based on API responses


@dataclass
class Module:
    """Represents a device/module."""

    id: str
    name: str
    type: str
    bridge: Optional[str] = None
    # Add other common attributes observed in homesdata/homestatus
    raw_data: Dict[str, Any] = None  # Store the raw dictionary


@dataclass
class Home:
    """Represents a home."""

    id: str
    name: str
    modules: List[Module]
    # Add other attributes from homesdata/homestatus if needed
    raw_data: Dict[str, Any] = None  # Store the raw dictionary


@dataclass
class Event:
    """Represents an event."""

    id: str
    type: str
    time: int
    # Add other event attributes
    raw_data: Dict[str, Any] = None  # Store the raw dictionary
