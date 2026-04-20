from __future__ import annotations

import json
import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import date
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from .llm_provider import get_provider, parse_json_response

logger = logging.getLogger(__name__)

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

try:
    from docx import Document
except ImportError:
    Document = None


TEXT_EXTENSIONS = {".md", ".txt", ".rst", ".pdf", ".docx"}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self.parts.append(text)

    def text(self) -> str:
        return "\n".join(self.parts)


@dataclass
class SourcePaths:
    source_dirs: list[Path]
    source_urls: list[str]
    model: str = "gemma4:latest"
    keep_alive: str = "10m"
    provider: str = "ollama"
    provider_config: dict[str, Any] = field(default_factory=dict)


@dataclass
class JobInfo:
    url: str
    title: str
    company: str
    requirements: list[str]


def _is_http_url(value: str) -> bool:
    return bool(re.match(r"^https?://", value.strip(), re.IGNORECASE))


def load_paths(config_path: Path) -> SourcePaths:
    data = json.loads(config_path.read_text(encoding="utf-8"))

    source_dirs_raw: list[str] = []
    if isinstance(data.get("sourcesDir"), list):
        source_dirs_raw = [s for s in data["sourcesDir"] if isinstance(s, str) and s.strip()]

    if not source_dirs_raw:
        raise ValueError(
            f"Missing or invalid source directories in {config_path}. "
            "Provide sourcesDir as a non-empty array of directory paths."
        )

    # Keep stable order while removing duplicates.
    deduped: list[str] = []
    seen: set[str] = set()
    for item in source_dirs_raw:
        if item not in seen:
            deduped.append(item)
            seen.add(item)

    dir_items = [Path(item) for item in deduped if not _is_http_url(item)]
    url_items = [item for item in deduped if _is_http_url(item)]

    provider = data.get("provider", "ollama").lower().strip()
    provider_config = data.get("providerConfig", {})

    return SourcePaths(
        source_dirs=dir_items,
        source_urls=url_items,
        model=data.get("model", "gemma4:latest"),
        keep_alive=data.get("keepAlive", "10m"),
        provider=provider,
        provider_config=provider_config,
    )


def _list_text_files(root: Path) -> list[Path]:
    if not root.exists() or not root.is_dir():
        return []
    return sorted(
        [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in TEXT_EXTENSIONS],
        key=lambda p: str(p).lower(),
    )


def _latest_text_file(root: Path) -> Path | None:
    files = _list_text_files(root)
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


def _pick_latest_cv(files: list[Path]) -> Path | None:
    if not files:
        return None

    cv_like = [p for p in files if re.search(r"\b(cv|resume|curriculum)\b", p.name, re.IGNORECASE)]
    pool = cv_like if cv_like else files
    return max(pool, key=lambda p: p.stat().st_mtime)


def _file_snapshot(paths: list[Path]) -> dict[str, dict[str, Any]]:
    snapshot: dict[str, dict[str, Any]] = {}
    for path in paths:
        stat = path.stat()
        snapshot[str(path)] = {"mtime": stat.st_mtime, "size": stat.st_size}
    return snapshot


def _extract_pdf_text(path: Path) -> str:
    if PdfReader is None:
        return f"[PDF file {path.name} - pypdf not installed]"
    try:
        reader = PdfReader(path)
        pages = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
        return "\n\n".join(pages) if pages else ""
    except Exception as e:
        return f"[Error reading PDF {path.name}: {e}]"


def _extract_docx_text(path: Path) -> str:
    if Document is None:
        return f"[DOCX file {path.name} - python-docx not installed]"
    try:
        doc = Document(path)
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n\n".join(paragraphs) if paragraphs else ""
    except Exception as e:
        return f"[Error reading DOCX {path.name}: {e}]"


def _read_text(path: Path) -> str:
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        return _extract_pdf_text(path)
    elif suffix == ".docx":
        return _extract_docx_text(path)

    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1", errors="ignore")


def _read_url_text(url: str) -> str:
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (JobHunterAssistant/1.0)"})
    with urlopen(req, timeout=20) as resp:
        raw = resp.read().decode("utf-8", errors="ignore")

    # Best effort: for HTML pages, reduce boilerplate to visible text.
    if "<html" in raw.lower() or "<body" in raw.lower():
        return _extract_job_text(raw)
    return raw


def _sample_voice_lines(text: str, max_samples: int = 4) -> list[str]:
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    picks: list[str] = []
    seen: set[str] = set()
    for s in sentences:
        # Keep moderately sized first-person lines that represent personal voice.
        if 45 <= len(s) <= 190 and re.search(r"\b(I|my|me)\b", s, re.IGNORECASE):
            key = s.lower()
            if key not in seen:
                picks.append(s)
                seen.add(key)
        if len(picks) >= max_samples:
            break
    return picks


def _extract_profile_llm(cv_text: str, app_text: str, tone_text: str, paths: SourcePaths) -> dict[str, Any]:
    provider = get_provider(
        paths.provider,
        paths.model,
        keep_alive=paths.keep_alive,
        **paths.provider_config,
    )
    
    instruction = (
        'Return a JSON object with exactly these keys:\n'
        '- "achievements": array of 6-8 professional achievements'
        ' (complete sentences with metrics/impact where available)\n'
        '- "identity": 1-2 sentences on who this candidate is professionally\n'
        '- "tone_description": 2-3 sentences on their natural writing style and voice\n'
        '- "skills": array of 6-8 top technical skills or domain areas\n'
        'Only use facts from the documents. Return ONLY valid JSON, no markdown fences.'
    )
    prompt = (
        f"Analyze these personal documents and extract a structured candidate profile.\n\n"
        f"{instruction}\n\n"
        f"=== LATEST CV ===\n{cv_text[:2500]}\n\n"
        f"=== RECENT APPLICATIONS ===\n{app_text[:2000]}\n\n"
        f"=== MOTIVATIONAL LETTERS ===\n{tone_text[:1500]}"
    )
    response = provider.chat(prompt)
    return parse_json_response(response)


def build_or_load_profile(paths: SourcePaths, cache_path: Path) -> dict[str, Any]:
    all_files: list[Path] = []
    for src_dir in paths.source_dirs:
        all_files.extend(_list_text_files(src_dir))

    # Deduplicate in case overlapping directories are configured.
    source_files = sorted({p.resolve() for p in all_files}, key=lambda p: str(p).lower())
    latest_cv = _pick_latest_cv(source_files)

    url_sources: list[dict[str, str]] = []
    for url in paths.source_urls:
        try:
            text = _read_url_text(url)
            if text.strip():
                digest = hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()
                url_sources.append({"url": url, "text": text, "sha256": digest})
        except Exception:
            # Ignore unreachable URLs and continue with available sources.
            continue

    if not source_files and not url_sources:
        raise FileNotFoundError("No readable source files found in configured directories or URLs.")

    snapshot = _file_snapshot(source_files)
    for src in url_sources:
        snapshot[f"url::{src['url']}"] = {"sha256": src["sha256"], "size": len(src["text"])}

    if cache_path.exists():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        cprofile = cached.get("profile", {})
        if (
            cached.get("snapshot") == snapshot
            and "identity" in cprofile
            and "tone_description" in cprofile
            and "voice_samples" in cprofile
        ):
            return cached

    recent_files = sorted(source_files, key=lambda p: p.stat().st_mtime, reverse=True)
    non_cv_files = [p for p in recent_files if latest_cv is None or p != latest_cv]

    cv_text = _read_text(latest_cv) if latest_cv else ""
    app_parts = [_read_text(p) for p in non_cv_files[:5]] + [s["text"] for s in url_sources[:3]]
    tone_parts = [_read_text(p) for p in non_cv_files[:3]] + [s["text"] for s in url_sources[:2]]
    app_text = "\n\n--- Next Document ---\n\n".join(part for part in app_parts if part.strip())
    tone_text = "\n\n--- Next Document ---\n\n".join(part for part in tone_parts if part.strip())
    voice_samples = _sample_voice_lines(tone_text if tone_text.strip() else app_text)

    llm_profile = _extract_profile_llm(cv_text, app_text, tone_text, paths)

    profile = {
        "snapshot": snapshot,
        "profile": {
            "latest_cv": str(latest_cv) if latest_cv else None,
            "cv_format": latest_cv.suffix.lower() if latest_cv else None,
            "source_directories_count": len(paths.source_dirs),
            "source_urls_count": len(url_sources),
            "source_files_count": len(source_files),
            "voice_samples": voice_samples,
            **llm_profile,
        },
    }
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    return profile


def _extract_job_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(unescape(html))
    return parser.text()


def _parse_job_text(text: str, source: str, paths: SourcePaths) -> JobInfo:
    provider = get_provider(
        paths.provider,
        paths.model,
        keep_alive=paths.keep_alive,
        **paths.provider_config,
    )
    
    prompt = (
        "Extract structured information from this job posting.\n"
        'Return a JSON object with these keys:\n'
        '- "role_title": the exact job title\n'
        '- "company": the hiring company name only (not the job board platform name)\n'
        '- "requirements": array of 5-8 specific requirements or responsibilities\n'
        'Return ONLY valid JSON.\n\n'
        f"=== JOB POSTING ===\n{text[:6000]}"
    )
    data = parse_json_response(provider.chat(prompt))
    return JobInfo(
        url=source,
        title=data.get("role_title", "Unknown Role"),
        company=data.get("company", "Unknown Company"),
        requirements=data.get("requirements", []),
    )


def fetch_job(url: str, paths: SourcePaths) -> JobInfo:
    logger.debug(f"Fetching job from URL: {url}")
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (JobHunterAssistant/1.0)"})
    with urlopen(req, timeout=20) as resp:
        raw = resp.read().decode("utf-8", errors="ignore")

    cleaned = _extract_job_text(raw)
    return _parse_job_text(cleaned, source=url, paths=paths)


def parse_job_from_text(text: str, paths: SourcePaths) -> JobInfo:
    """Parse a JobInfo from a raw job description string (no network request)."""
    return _parse_job_text(text.strip(), source="(pasted description)", paths=paths)


def draft_cover_letter(
    profile: dict[str, Any],
    job: JobInfo,
    paths: SourcePaths,
    role_override: str | None = None,
) -> str:
    provider = get_provider(
        paths.provider,
        paths.model,
        keep_alive=paths.keep_alive,
        **paths.provider_config,
    )
    
    role_text = role_override.strip() if role_override else job.title
    pdata = profile.get("profile", {})
    achievements = json.dumps(pdata.get("achievements", [])[:6])
    skills = ", ".join(pdata.get("skills", [])[:8])
    identity = pdata.get("identity", "")
    tone = pdata.get("tone_description", "professional and direct")
    voice_samples = pdata.get("voice_samples", [])[:4]
    voice_block = "\n".join(f"- {line}" for line in voice_samples)
    reqs = "\n".join(f"- {r}" for r in job.requirements[:6])
    prompt = (
        f"Write a tailored professional cover letter.\n\n"
        f"CANDIDATE:\n"
        f"- Identity: {identity}\n"
        f"- Key achievements: {achievements}\n"
        f"- Skills: {skills}\n"
        f"- Writing tone: {tone}\n\n"
        f"VOICE EXAMPLES (style anchors from candidate's own writing):\n{voice_block}\n\n"
        f"TARGET ROLE: {role_text}\n"
        f"COMPANY: {job.company}\n"
        f"REQUIREMENTS:\n{reqs}\n\n"
        f"INSTRUCTIONS:\n"
        f"- Salutation: 'Dear Hiring Team,'\n"
        f"- Open with specific motivation for this role at {job.company}\n"
        f"- Reference 2-3 achievements most relevant to the requirements listed\n"
        f"- Mirror the candidate's natural writing tone and sentence rhythm from the voice examples\n"
        f"- Keep wording human, specific, and personal; avoid generic AI-sounding phrases\n"
        f"- Do NOT use phrases like: 'deep-seated belief', 'catalyst for', 'I am writing to express', 'I am confident that'\n"
        f"- Prefer short to medium sentences and concrete language over grand abstractions\n"
        f"- 220-320 words total\n"
        f"- Plain paragraphs only, no bullet points or section headers inside the letter\n"
        f"- Close with a brief confident call to action\n"
        f"- Return only the letter text, nothing else"
    )
    return provider.chat(prompt)


def save_cover_letter(content: str, company: str, output_dir: Path) -> Path:
    company_slug = re.sub(r"[^a-z0-9]+", "-", company.lower()).strip("-") or "company"
    filename = f"{date.today().isoformat()}-{company_slug}-cover-letter.md"
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / filename
    target.write_text(content + "\n", encoding="utf-8")
    return target
