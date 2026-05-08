from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Callable, Sequence

from audio import canonical_to_plain_script, raw_to_plain_script, validate_plain_script
from audio.doctor import build_arg_parser as build_doctor_arg_parser
from audio.doctor import main as doctor_main
from audio.make_audio_edge_tts import main as render_audio_main
from audio.render_cli_adapter import build_render_audio_arg_parser


CommandHandler = Callable[[Sequence[str] | None], None]
ParserFactory = Callable[[], argparse.ArgumentParser]


@dataclass(frozen=True)
class CommandSpec:
    name: str
    help: str
    handler: CommandHandler
    parser_factory: ParserFactory


COMMANDS: tuple[CommandSpec, ...] = (
    CommandSpec(
        "canonical-to-plain",
        "Convert canonical authoring JSON to plain script.",
        canonical_to_plain_script.main,
        canonical_to_plain_script.build_arg_parser,
    ),
    CommandSpec(
        "raw-to-plain",
        "Convert raw text to plain script with safe default tags.",
        raw_to_plain_script.main,
        raw_to_plain_script.build_arg_parser,
    ),
    CommandSpec(
        "validate-plain",
        "Validate a plain script before rendering.",
        validate_plain_script.main,
        validate_plain_script.build_arg_parser,
    ),
    CommandSpec(
        "render-audio",
        "Render audio from a plain script via Edge TTS + mix pipeline.",
        render_audio_main,
        build_render_audio_arg_parser,
    ),
    CommandSpec(
        "doctor",
        "Inspect runtime health and expected project assets.",
        doctor_main,
        build_doctor_arg_parser,
    ),
)

_COMMAND_MAP = {command.name: command for command in COMMANDS}


def _clone_actions(source: argparse.ArgumentParser, target: argparse.ArgumentParser) -> None:
    for action in source._actions:
        if isinstance(action, argparse._HelpAction):
            continue
        kwargs = {
            "default": action.default,
            "required": action.required,
            "help": action.help,
        }
        if action.choices is not None:
            kwargs["choices"] = action.choices
        if getattr(action, "nargs", None) is not None:
            kwargs["nargs"] = action.nargs
        if getattr(action, "type", None) is not None:
            kwargs["type"] = action.type
        if action.metavar is not None:
            kwargs["metavar"] = action.metavar

        action_name = action.__class__.__name__
        if action_name == "_StoreTrueAction":
            target.add_argument(*action.option_strings, dest=action.dest, action="store_true", help=action.help, default=action.default)
            continue
        if action_name == "_StoreFalseAction":
            target.add_argument(*action.option_strings, dest=action.dest, action="store_false", help=action.help, default=action.default)
            continue
        if getattr(action, "const", None) is not None:
            kwargs["const"] = action.const
        target.add_argument(*action.option_strings, dest=action.dest, action="store", **kwargs)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Unified CLI for Render Audio.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in COMMANDS:
        command_parser = subparsers.add_parser(command.name, help=command.help, description=command.help)
        _clone_actions(command.parser_factory(), command_parser)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    argv_list = list(argv) if argv is not None else None
    args = build_parser().parse_args(argv_list)
    command = _COMMAND_MAP[args.command]
    forwarded = argv_list[1:] if argv_list is not None else None
    command.handler(forwarded)


def gui_entrypoint(argv: Sequence[str] | None = None) -> None:
    _ = argv
    from audio.gui.app import main as gui_main

    gui_main(None)

