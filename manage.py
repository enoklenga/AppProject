#!/usr/bin/env python
import os
import sys


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Django non è disponibile. Avvia il progetto tramite Docker "
            "oppure installa le dipendenze del pyproject.toml."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
