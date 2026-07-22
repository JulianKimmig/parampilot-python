"""Probe an installed public wheel from outside its source repository."""

from __future__ import annotations

from importlib.util import find_spec

from parampilot import AsyncParamPilot, ParamPilot
from parampilot.operations import operation_registry

PROHIBITED_MODULES = (
    "bofire",
    "django",
    "parampilot_backend",
    "parampilot_codegen",
    "parampilot_release",
    "parampilot_worker",
)


def main() -> None:
    """Assert standalone wheel imports, coverage, and private-module absence."""
    assert AsyncParamPilot.__name__ == "AsyncParamPilot"
    assert ParamPilot.__name__ == "ParamPilot"
    assert len(operation_registry()) == 39
    assert not [name for name in PROHIBITED_MODULES if find_spec(name) is not None]


if __name__ == "__main__":
    main()
