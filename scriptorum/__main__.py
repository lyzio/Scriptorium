"""Run Scriptorum: ``python -m scriptorum [adventure.scav]``."""

import sys

if __name__ == "__main__":
    if "--scriptorum-build-helper" in sys.argv[1:]:
        # F7.1 (M6): an installed app runs its own build helper this way.
        from scriptorum.core.helper import serve

        serve()
        sys.exit(0)
    from scriptorum.app.main import main

    sys.exit(main())
