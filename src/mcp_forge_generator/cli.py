from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .generator import generate_project


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mcp-forge",
        description="Generate production-grade FastMCP server from OpenAPI/Swagger spec",
    )
    parser.add_argument("--input", help="Path to OpenAPI file (json/yaml/yml)")
    parser.add_argument("--output", help="Output directory for generated server")
    parser.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help="Prompt for arguments interactively (press Enter to accept defaults)",
    )
    return parser


def _prompt_with_default(prompt: str, default: str) -> str:
    raw = input(f"{prompt} [{default}]: ").strip()
    return raw if raw else default


def _resolve_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> tuple[Path, Path]:
    default_input = args.input or "petstore.yaml"
    default_output = args.output or "generated_server"

    if args.interactive:
        if not sys.stdin.isatty():
            parser.error("--interactive requires a TTY (interactive terminal)")
        input_spec = _prompt_with_default("OpenAPI spec path", default_input)
        output_dir = _prompt_with_default("Output directory", default_output)
        return Path(input_spec), Path(output_dir)

    if not args.input or not args.output:
        parser.error("--input and --output are required unless --interactive is used")

    return Path(args.input), Path(args.output)


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    input_spec, output_dir = _resolve_args(parser, args)

    generate_project(input_spec=input_spec, output_dir=output_dir)
    print(f"Generated FastMCP server at: {output_dir}")


if __name__ == "__main__":
    main()
