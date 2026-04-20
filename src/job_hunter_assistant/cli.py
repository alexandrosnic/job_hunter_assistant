from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

from .workflow import build_or_load_profile, draft_cover_letter, fetch_job, load_paths, parse_job_from_text, save_cover_letter

logger = logging.getLogger(__name__)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a tailored cover letter from a job posting using your local documents.\n\n"
            "SETUP:\n"
            "  1. Copy config/config.example.json to .local/config.json\n"
            "  2. Edit .local/config.json with your source directories and AI model\n"
            "  3. Ensure Ollama is running: ollama serve\n"
            "  4. Pull your model: ollama pull gemma4:latest (or your chosen model)\n\n"
            "USAGE:\n"
            "  Pass a job URL, description file, stdin, or paste interactively."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "job_input",
        nargs="?",
        default=None,
        help="Job posting URL, local file path, '-' for stdin, or omit to paste interactively",
    )
    parser.add_argument("--role", help="Override detected role title", default=None)
    parser.add_argument("--save", action="store_true", help="Save draft without prompting")
    parser.add_argument(
        "--workspace",
        default=".",
        help="Workspace root (contains .local/config.json)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args(argv)


def _is_url(value: str) -> bool:
    return bool(re.match(r"^https?://", value.strip(), re.IGNORECASE))


def _read_job_input(job_input: str | None) -> tuple[str | None, str | None]:
    """Return (url, raw_text). Exactly one of them will be set."""
    if job_input is None:
        print("Paste the job description below. Enter a blank line followed by EOF (Ctrl+D) when done:")
        lines = []
        try:
            for line in sys.stdin:
                lines.append(line)
        except KeyboardInterrupt:
            return None, None
        return None, "".join(lines).strip()

    if job_input == "-":
        return None, sys.stdin.read().strip()

    if _is_url(job_input):
        return job_input, None

    path = Path(job_input)
    if path.exists() and path.is_file():
        return None, path.read_text(encoding="utf-8").strip()

    # Treat it as raw description text passed directly on the command line.
    return None, job_input.strip()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    
    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stderr)],
    )
    logger.debug(f"Job Hunter Assistant CLI started (verbose={args.verbose})")
    
    root = Path(args.workspace).resolve()

    config_path = root / ".local" / "config.json"
    cache_path = root / ".local" / "candidate-profile-cache.json"
    output_dir = root / "output" / "cover-letters"

    if not config_path.exists():
        error_msg = (
            f"Config file not found: {config_path}\n\n"
            f"Setup steps:\n"
            f"  1. mkdir -p {root / '.local'}\n"
            f"  2. cp {root / 'config' / 'config.example.json'} {config_path}\n"
            f"  3. Edit {config_path} with your source directories and model\n"
        )
        print(error_msg)
        logger.error(f"Missing config: {config_path}")
        return 2

    job_url, job_text = _read_job_input(args.job_input)

    if not job_url and not job_text:
        print("Error: no job input provided.")
        return 2

    try:
        logger.info("Loading configuration...")
        paths = load_paths(config_path)
        logger.info(f"Using provider: {paths.provider}, model: {paths.model}")
        
        print("Building candidate profile from your documents...")
        logger.debug(f"Loading from: {[str(p) for p in paths.source_dirs]}")
        profile = build_or_load_profile(paths, cache_path)
        logger.info("Profile built/loaded successfully")
        
        print("Parsing job posting...")
        if job_url:
            logger.debug(f"Fetching job from URL: {job_url}")
            job = fetch_job(job_url, paths)
        else:
            logger.debug("Parsing job from text input")
            job = parse_job_from_text(job_text, paths)  # type: ignore[arg-type]
        logger.info(f"Job parsed: {job.company} - {job.title}")
        
        print("Drafting cover letter...")
        letter = draft_cover_letter(
            profile,
            job,
            paths,
            role_override=args.role,
        )
        logger.info("Cover letter drafted successfully")
    except RuntimeError as exc:
        print(f"\nSetup Error: {exc}", file=sys.stderr)
        logger.error(f"Runtime error: {exc}")
        return 1
    except Exception as exc:
        print(f"\nError: {exc}", file=sys.stderr)
        logger.exception(f"Unexpected error: {exc}")
        return 1

    print("\n=== Cover Letter Draft ===\n")
    print(letter)

    should_save = args.save
    if not args.save:
        answer = input("\nSave draft to output/cover-letters? [y/N]: ").strip().lower()
        should_save = answer in {"y", "yes"}

    if should_save:
        target = save_cover_letter(letter, job.company, output_dir)
        print(f"\nSaved: {target}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
