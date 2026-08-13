"""PetJourney domain schemas, re-exported for backward-compatible imports.

Splitting note: the original single-file ``app/schemas.py`` held 117 classes and
enums. They are now grouped by resource domain under this package. The import
surface (``from .schemas import X`` / ``from app.schemas import X``) is preserved
unchanged via the wildcard re-exports below.
"""

from .base import *  # noqa: F401,F403
from .memory import *  # noqa: F401,F403
from .pet import *  # noqa: F401,F403
from .economy import *  # noqa: F401,F403
from .place import *  # noqa: F401,F403
from .travel import *  # noqa: F401,F403
from .world import *  # noqa: F401,F403
from .guide import *  # noqa: F401,F403
from .auth import *  # noqa: F401,F403
