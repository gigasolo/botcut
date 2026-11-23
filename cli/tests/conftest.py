"""Shared by every test."""

import pytest


@pytest.fixture(autouse=True)
def _no_names_of_the_persons_own(monkeypatch, tmp_path_factory):
    """A test never reads the names list of whoever is running it."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path_factory.mktemp("config")))


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """A test that does not stand in for the network does not reach it."""

    def refuse(*_args, **_kwargs):
        raise AssertionError("a test reached the network")

    monkeypatch.setattr("botcut.net.requests.post", refuse)
    monkeypatch.setattr("botcut.net.requests.get", refuse, raising=False)
