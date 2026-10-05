"""Do not load a host GTK desktop theme during headless Qt checks."""

import os

if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
    os.environ["QT_QPA_PLATFORMTHEME"] = ""
    os.environ["QT_STYLE_OVERRIDE"] = "Fusion"
