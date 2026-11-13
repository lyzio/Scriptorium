"""Run Scriptorum: ``python -m scriptorum [adventure.scav]``."""

import sys

if __name__ == "__main__":
    if "--scriptorum-build-helper" in sys.argv[1:]:
        # F7.1 (M6): an installed app runs its own build helper this way,
        # from the same version folder as the app (F22).
        from scriptorum.boot import helper_path

        helper_path()
        from scriptorum.core.helper import serve

        serve()
        sys.exit(0)
    # F22 (M6 part C5): the start-up step runs a newer verified version from
    # the author's own Scriptorum folder, or this installed version.
    from scriptorum.boot import run

    sys.exit(run())
