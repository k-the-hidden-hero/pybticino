"""Tests for pybticino data models."""

from pybticino.models import Event, Home, Module


def test_module_defaults():
    """Test Module dataclass defaults."""
    mod = Module(id="m1", name="Test", type="BNDL")
    assert mod.id == "m1"
    assert mod.bridge is None
    assert mod.raw_data == {}


def test_module_with_raw_data():
    """Test Module with raw_data preserves all fields."""
    raw = {"id": "m1", "name": "Test", "type": "BNDL", "firmware": "1.0", "custom_field": 42}
    mod = Module(id="m1", name="Test", type="BNDL", raw_data=raw)
    assert mod.raw_data["firmware"] == "1.0"
    assert mod.raw_data["custom_field"] == 42


def test_home_with_modules():
    """Test Home with a list of modules."""
    m1 = Module(id="m1", name="Lock", type="BNDL")
    m2 = Module(id="m2", name="Light", type="BNSL")
    home = Home(id="h1", name="Casa", modules=[m1, m2])
    assert len(home.modules) == 2
    assert home.modules[0].id == "m1"


def test_home_empty_modules():
    """Test Home with no modules."""
    home = Home(id="h1", name="Empty Home", modules=[])
    assert home.modules == []
    assert home.raw_data == {}


def test_event_dataclass():
    """Test Event dataclass."""
    raw = {"id": "e1", "type": "call", "time": 1700000000, "module_id": "ext1"}
    evt = Event(id="e1", type="call", time=1700000000, raw_data=raw)
    assert evt.time == 1700000000
    assert evt.raw_data["module_id"] == "ext1"


def test_module_equality():
    """Test that two modules with same data are equal."""
    m1 = Module(id="m1", name="Lock", type="BNDL")
    m2 = Module(id="m1", name="Lock", type="BNDL")
    assert m1 == m2


def test_module_inequality():
    """Test that modules with different IDs are not equal."""
    m1 = Module(id="m1", name="Lock", type="BNDL")
    m2 = Module(id="m2", name="Lock", type="BNDL")
    assert m1 != m2
