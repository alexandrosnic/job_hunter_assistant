import os
import logging
from pathlib import Path
from typing import List, Optional
import base64
import datetime
import mimetypes

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Load environment variables from .env if present
load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

from src.job_hunter_assistant.workflow import (
    SourcePaths,
    build_or_load_profile,
    draft_cover_letter,
    fetch_job,
    parse_job_from_text,
    save_cover_letter,
    _is_http_url
)
from src.job_hunter_assistant.pdf_exporter import save_cover_letter_pdf

app = FastAPI(title="Job Hunter Assistant API")

# Load API key from environment
API_KEY = os.getenv("JH_API_KEY", "")
if API_KEY:
    logger.info("API authentication enabled (JH_API_KEY is set)")
else:
    logger.warning("API authentication disabled - set JH_API_KEY environment variable for security")

def verify_api_key(authorization: Optional[str] = Header(None)) -> None:
    """Verify API key for protected endpoints. Skip if API_KEY not set."""
    if not API_KEY:
        return  # No API key configured; allow all requests
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid API key")
    token = authorization[7:]
    if token != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")

# Mount the static frontend directory
frontend_dir = Path("frontend")
if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory="frontend"), name="static")

class GenerateRequest(BaseModel):
    sources_dir: List[str]
    job_url: Optional[str] = None
    job_text: Optional[str] = None
    role: Optional[str] = None
    model: str = "gemma4:latest"
    keep_alive: str = "10m"
    provider: str = "ollama"
    provider_config: dict = {}
    output_dir: Optional[str] = None
    save_as_pdf: bool = False
    candidate_name: Optional[str] = None
    candidate_contact: Optional[str] = None
    template_style: str = "modern"

class SavePdfRequest(BaseModel):
    pdf_base64: str
    company_slug: str
    output_dir: Optional[str] = None


def _build_download_url(path: Path) -> str:
    return f"/api/download/{path.name}"

@app.post("/api/generate")
def generate_cover_letter(req: GenerateRequest, _: None = Depends(verify_api_key)):
    logger.info(f"Generating cover letter for {req.role or 'unknown role'} at {req.model}")
    if not req.job_url and not req.job_text:
        logger.warning("Request missing job_url and job_text")
        raise HTTPException(status_code=400, detail="Must provide either job_url or job_text")
    if not req.sources_dir:
        logger.warning("Request missing sources_dir")
        raise HTTPException(status_code=400, detail="Must provide at least one source directory or URL")

    # Parse sources
    source_dirs: list[Path] = []
    source_urls: list[str] = []
    
    for src in req.sources_dir:
        if _is_http_url(src):
            source_urls.append(src)
        else:
            p = Path(src)
            if not p.exists() or not p.is_dir():
                # Allow it to bypass here, build_or_load_profile uses rglob which will just be skipped if it doesn't exist
                pass
            source_dirs.append(p)
            
    paths = SourcePaths(
        source_dirs=source_dirs,
        source_urls=source_urls,
        model=req.model,
        keep_alive=req.keep_alive,
        provider=req.provider,
        provider_config=req.provider_config,
    )
    
    # We will use the standard local cache path from standard CLI
    root = Path.cwd()
    cache_path = root / ".local" / "candidate-profile-cache.json"
    
    # Load optional PDF template overrides
    pdf_template: dict | None = None
    pdf_template_path = root / ".local" / "pdf-template.json"
    if pdf_template_path.exists():
        import json
        try:
            raw = json.loads(pdf_template_path.read_text(encoding="utf-8"))
            # Strip comment keys before use
            pdf_template = {k: v for k, v in raw.items() if not k.startswith("_")}
            logger.info("Loaded PDF template overrides from .local/pdf-template.json")
        except Exception as e:
            logger.warning(f"Could not parse pdf-template.json: {e}")
    
    try:
        logger.info("Building candidate profile...")
        profile = build_or_load_profile(paths, cache_path)
        logger.info("Profile ready")
    except Exception as e:
        logger.error(f"Failed to build profile: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Error building profile: {e}")
        
    try:
        logger.info(f"Parsing job input (URL: {bool(req.job_url)})...")
        if req.job_url:
            job = fetch_job(req.job_url, paths)
        else:
            job = parse_job_from_text(req.job_text, paths)
        logger.info(f"Job parsed: {job.company} - {job.title}")
    except RuntimeError as e:
        logger.error(f"Setup/LLM error during job parsing: {e}")
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"Error parsing job: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Error parsing job: {e}")
        
    try:
        logger.info("Drafting cover letter...")
        letter = draft_cover_letter(
            profile,
            job,
            paths,
            role_override=req.role,
        )
        logger.info(f"Cover letter drafted ({len(letter)} chars)")
    except RuntimeError as e:
        logger.error(f"Setup/LLM error during drafting: {e}")
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"Error drafting letter: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error drafting letter: {e}")
        
    # Handle Output Saving
    saved_path_str = None
    download_url = None
    if req.save_as_pdf or req.output_dir:
        try:
            logger.info(f"Saving output (PDF: {req.save_as_pdf})...")
            if req.save_as_pdf:
                saved_target = save_cover_letter_pdf(
                    content=letter,
                    company=job.company,
                    output_dir=req.output_dir,
                    name=req.candidate_name,
                    contact=req.candidate_contact,
                    style=req.template_style,
                    template=pdf_template,
                )
            else:
                out_dir_path = Path(req.output_dir) if req.output_dir else Path("output/cover-letters")
                saved_target = save_cover_letter(letter, job.company, out_dir_path)
            
            saved_path_str = str(saved_target)
            if req.save_as_pdf:
                download_url = _build_download_url(saved_target)
            logger.info(f"Document saved: {saved_target}")
        except Exception as e:
            logger.error(f"Failed to save document: {e}", exc_info=True)
            if req.save_as_pdf:
                raise HTTPException(status_code=500, detail=f"PDF generation failed: {e}")
            
    return {
        "letter": letter,
        "saved_path": saved_path_str,
        "download_url": download_url,
        "output_format": "pdf" if req.save_as_pdf else "text",
    }

@app.post("/api/save_pdf_blob")
def save_pdf_blob(req: SavePdfRequest, _: None = Depends(verify_api_key)):
    # Validate base64 content is actually PDF
    try:
        pdf_bytes = base64.b64decode(req.pdf_base64)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid base64: {e}")
    
    # Check PDF magic number (should start with %PDF)
    if not pdf_bytes.startswith(b'%PDF'):
        raise HTTPException(status_code=400, detail="File is not a valid PDF (invalid magic bytes)")
    
    out_dir_path = Path(req.output_dir) if req.output_dir else Path("output/cover-letters")
    out_dir_path.mkdir(parents=True, exist_ok=True)
    
    filename = f"{datetime.date.today().isoformat()}-{req.company_slug}-cover-letter.pdf"
    target = out_dir_path / filename
    
    target.write_bytes(pdf_bytes)
    return {"saved_path": str(target)}


@app.get("/api/download/{filename}")
def download_generated_file(filename: str, _: None = Depends(verify_api_key)):
    base_dir = (Path.cwd() / "output" / "cover-letters").resolve()
    target = (base_dir / filename).resolve()

    if target.parent != base_dir or not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    media_type, _ = mimetypes.guess_type(target.name)
    return FileResponse(
        str(target),
        media_type=media_type or "application/octet-stream",
        content_disposition_type="inline",
    )

@app.get("/")
def serve_index():
    logger.debug("Serving index.html")
    index_path = frontend_dir / "index.html"
    if not index_path.exists():
        logger.error(f"index.html not found at {index_path}")
        raise HTTPException(status_code=404, detail="Frontend index.html not found.")
    return FileResponse(str(index_path))

@app.get("/{filename}")
def serve_static(filename: str):
    logger.debug(f"Serving static file: {filename}")
    file_path = frontend_dir / filename
    if file_path.exists() and file_path.is_file():
        return FileResponse(str(file_path))
    logger.warning(f"Static file not found: {filename}")
    raise HTTPException(status_code=404, detail="File not found")

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting Job Hunter Assistant API...")
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
