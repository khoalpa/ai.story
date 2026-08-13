from __future__ import annotations

def test_audio_cli_builds_boolean_optional_actions() -> None:
    from audio.entrypoints import build_parser

    args = build_parser().parse_args(["render-audio", "--no-quality-gate"])

    assert args.command == "render-audio"
    assert args.quality_gate is False


def test_audio_cli_forwards_explicit_subcommand_arguments(monkeypatch) -> None:
    import audio.entrypoints as entrypoints

    forwarded: list[str] = []
    command = entrypoints._COMMAND_MAP["validate-plain"]
    monkeypatch.setitem(
        entrypoints._COMMAND_MAP,
        "validate-plain",
        entrypoints.CommandSpec(command.name, command.help, forwarded.extend, command.parser_factory),
    )

    entrypoints.main(["validate-plain", "--input", "story.txt", "--json"])

    assert forwarded == ["--input", "story.txt", "--json"]
