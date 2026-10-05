"""Do not load a host GTK desktop theme during headless Qt checks."""

import os

import pytest

if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
    os.environ["QT_QPA_PLATFORMTHEME"] = ""
    os.environ["QT_STYLE_OVERRIDE"] = "Fusion"


@pytest.fixture(autouse=True)
def isolated_user_preferences(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
