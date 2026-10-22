"""AX Branch — Owner-governed autonomous execution. Python 3.11+, standard library only."""
import os
import sys
from pathlib import Path

__version__ = '0.1.49'


def _root():
    """The AX-Branch workspace root: the folder holding workspace/ and obsidian/."""
    if os.environ.get('AXB_ROOT'):
        return Path(os.environ['AXB_ROOT'])
    here = Path(sys.executable if getattr(sys, 'frozen', False) else __file__).resolve()
    for parent in here.parents:
        if (parent / 'workspace').is_dir() and (parent / 'obsidian').is_dir():
            return parent
    return here.parent


ROOT = _root()
WORKSPACE = ROOT / 'workspace'
VAULT = ROOT / 'obsidian' / 'AX-Branch-Vault' / 'Branch_DB'
DB_PATH = WORKSPACE / 'axbranch.sqlite3'
# Global AI Intelligence's live library, opened read-only. Its owner forbids writes.
GAI_DB = Path(os.environ.get('AXB_GAI_DB') or
              Path.home() / 'Desktop' / 'AI-Trend-Collector' / 'data' / 'ai_intelligence.db')
