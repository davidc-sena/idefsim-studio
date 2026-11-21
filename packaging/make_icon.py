"""Gera as imagens da identidade visual a partir de idefsim/gui/branding.py.

- idefsim/resources/icon.png  (1024 px, ícone dos executáveis)
- docs/logo.png               (janela de abertura, para o README)

Uso:  python packaging/make_icon.py
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

from idefsim.gui import branding  # noqa: E402

app = QApplication([])
branding.mark_pixmap(1024).save(str(ROOT / "idefsim" / "resources" / "icon.png"))
branding.splash_pixmap(2, status=None).save(str(ROOT / "docs" / "logo.png"))
print("ícone e logo atualizados")
