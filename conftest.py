from __future__ import annotations

import os
import sys

# Prevent the active test session from writing bytecode into the repository,
# which would otherwise make artifact-hygiene checks flaky.
sys.dont_write_bytecode = True
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
