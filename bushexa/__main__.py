"""Enable ``python -m bushexa`` by delegating to the CLI entry point."""

from bushexa.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
