# Security Policy

## Important: This tool is for Local Use Only

Job Hunter Assistant is designed for **personal, local use**. Do not expose the API to the internet without proper security hardening.

## API Authentication

To protect your local instance, you can enable API key authentication:

```bash
export JH_API_KEY="your-secure-random-key-here"
python app.py
```

When `JH_API_KEY` is set, all API endpoints (`/api/generate`, `/api/save_pdf_blob`, `/api/download/*`) require a Bearer token:

```bash
curl -H "Authorization: Bearer your-secure-random-key-here" \
  -X POST http://127.0.0.1:8000/api/generate \
  -H "Content-Type: application/json" \
  -d '{"sources_dir": [...], "job_url": "..."}'
```

If `JH_API_KEY` is not set, the API allows all requests (suitable only for local development).

## Security Considerations

### File Access
- Generated PDF and text files are stored in `output/cover-letters/` and are **world-readable by default** on shared systems.
- Restrict file permissions: `chmod 700 output/cover-letters/`

### Local Ollama Inference
- This tool relies on a local Ollama instance. If Ollama is compromised, cover letter content and candidate data may be exposed.
- Run Ollama on a trusted, isolated machine.

### Candidate Data
- All documents (CVs, past applications, cover letters) are loaded into memory and sent to Ollama for RAG analysis.
- Do not expose the API to untrusted networks.

### Input Validation
- The CLI accepts job URLs and job text; always verify the source before using untrusted URLs.
- PDF uploads are validated against the PDF magic number to prevent arbitrary file writes.

## Reporting Security Issues

Do not open public issues for security vulnerabilities. If you discover a security issue:

1. **Do not** publicly disclose it.
2. Contact the maintainers privately.
3. Allow time for a fix before public disclosure.

## Recommended Hardening for Production Use

If you must expose this tool beyond your local machine:

1. **Add authentication** (API key, OAuth, etc.)—the API key feature is provided for this.
2. **Use HTTPS** with a reverse proxy (nginx, Caddy, etc.)
3. **Add rate limiting** to prevent DOS attacks.
4. **Audit logging** to track all generation requests.
5. **Separate candidate data** from the inference pipeline for data isolation.
6. **Regular backups** and access controls for `output/cover-letters/`.
7. **Minimize permissions** on the process running the app.

## Dependency Security

Run `pip audit` regularly to check for known vulnerabilities in dependencies:

```bash
pip audit
```

Version-pinned dependencies in `requirements.txt` help ensure reproducible, auditable installs.

## Running Behind a Proxy

If you deploy this to a shared environment, use a reverse proxy to:
- Add authentication
- Enforce HTTPS
- Rate-limit requests
- Log access

Example nginx configuration:
```nginx
location /api/ {
    proxy_pass http://127.0.0.1:8000;
    auth_request /auth;
    limit_req zone=api burst=10 nodelay;
}
```

## Responsible Disclosure

Thank you for helping keep Job Hunter Assistant safe and secure.
