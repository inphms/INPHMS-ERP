import contextlib
import sys
from .command import Command
from inphms import config

COMMAND = None

def main():
    global COMMAND

    args = sys.argv[1:]

    if len(args) > 1 and args[0].startswith('--addons-path=') and not args[1].startswith('-'):
        config._parse_config([args[0]])
        args = args[1:]
    if len(args) and not args[0].startswith('-'):
        # specified command
        command_name = args[0]
        args = args[1:]
    elif 'h' in args or '--help' in args:
        # help command
        command_name = 'help'
        args = [x for x in args if x not in ('-h', '--help')]
    else:
        # default command
        command_name = 'server'
    
    if command:=find_command(command_name):
        COMMAND = command
        command().run(args)
    else:
        sys.exit(f">>> Unknown command: {command_name}")

def find_command(name:str) -> type[Command] | None:
    with contextlib.suppress(ImportError):
        __import__(f"inphms.cli.{name}")
    return Command._command_list.get(name)