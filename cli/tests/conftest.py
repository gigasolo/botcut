"""Shared by every test."""

import pytest


@pytest.fixture(autouse=True)
def _no_names_of_the_persons_own(monkeypatch, tmp_path_factory):
    """A test never reads the names list of whoever is running it."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path_factory.mktemp("config")))
