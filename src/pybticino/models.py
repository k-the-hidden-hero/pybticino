"""Data models for pybticino."""

from dataclasses import dataclass, field
from typing import Any, Optional

# Placeholder models - To be refined based on API responses


@dataclass
class Module:
    """Represents a single BTicino/Netatmo device or module.

    Attributes:
        id (str): The unique identifier of the module (MAC address or similar).
        name (str): The user-defined name of the module.
        type (str): The type identifier of the module (e.g., 'BNDL' for door lock).
        bridge (Optional[str]): The ID of the bridge module this module is connected to,
                                 if applicable. None for main/bridge modules.
        raw_data (dict[str, Any]): The raw dictionary representation of the module
                                   as received from the API. Useful for accessing
                                   less common or undocumented attributes.

    """

    id: str
    name: str
    type: str
    bridge: Optional[str] = None
    # Add other common attributes observed in homesdata/homestatus
    raw_data: dict[str, Any] = field(default_factory=dict)  # Store the raw dictionary


@dataclass
class Home:
    """Represents a BTicino/Netatmo home installation.

    Attributes:
        id (str): The unique identifier of the home.
        name (str): The user-defined name of the home.
        modules (list[Module]): A list of Module objects belonging to this home.
        raw_data (dict[str, Any]): The raw dictionary representation of the home
                                   as received from the API.

    """

    id: str
    name: str
    modules: list[Module]
    # Add other attributes from homesdata/homestatus if needed
    raw_data: dict[str, Any] = field(default_factory=dict)  # Store the raw dictionary


@dataclass
class Event:
    """Represents an event recorded by the BTicino/Netatmo system.

    Attributes:
        id (str): The unique identifier of the event.
        type (str): The type of the event (e.g., 'doorbell_ring', 'person_seen').
        time (int): The timestamp (Unix epoch) when the event occurred.
        raw_data (dict[str, Any]): The raw dictionary representation of the event
                                   as received from the API. Contains additional
                                   details specific to the event type.

    """

    id: str
    type: str
    time: int
    # Add other event attributes
    raw_data: dict[str, Any] = field(default_factory=dict)  # Store the raw dictionary
