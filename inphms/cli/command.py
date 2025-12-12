from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from inspect import cleandoc
import sys
import re
import argparse


COMMAND_NAME_RE = re.compile(r'^[a-z][a-z0-9_]*$', re.I)
PROG_NAME = Path(sys.argv[0]).name

class Command(ABC):
    _command_list: dict[str, type[Command]] = {}
    description = None
    epilog = None
    _parser = None

    name: str | None = None

    def __init_subclass__(cls) -> None:
        cls.name = cls.name or cls.__name__.lower()
        module = cls.__module__.rpartition(".")[2]
        if not cls.is_valid_command_name(cls.name):
            raise ValueError(f"Invalid command name {cls.name!r} for {module}")
        if cls.name != module:
            raise ValueError(f"Command name {cls.name!r} conflicts with module name {module}")
        cls._command_list[cls.name] = cls

    @property
    def prog(self):
        return f"{PROG_NAME} [--addons-path=PATH,...] {self.name}"
    
    @property
    def parser(self):
        if not self._parser:
            self._parser = argparse.ArgumentParser(
                formatter_class=argparse.RawDescriptionHelpFormatter,
                prog=self.prog,
                description=cleandoc(self.description or self.__doc__ or ""),
                epilog=cleandoc(self.epilog or ""),
            )
        return self._parser

    @classmethod
    def is_valid_command_name(cls, name: str) -> bool:
        return bool(re.match(COMMAND_NAME_RE, name))

    @abstractmethod
    def run(self, args: list[str]) -> None:
        """ Main method to run command """