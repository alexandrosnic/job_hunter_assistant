# Changelog

## [Unreleased]

### Added
- **Multi-provider LLM support**: Switch between Ollama (local), OpenAI, or Anthropic APIs via config file
- **PDF vs text output**: Toggle between PDF export (opens in new tab) or inline text display
- **Environment configuration**: `.env` file support for API keys and Ollama host configuration
- **Enhanced logging**: Debug and info level logging throughout CLI and API
- **API authentication**: Optional Bearer token authentication via `JH_API_KEY` environment variable
- **Security hardening**: PDF magic byte validation, CORS consideration, security documentation

### Changed
- **Config file renamed**: `job-agent-paths.json` → `config.json` for clarity
- **Dead code removal**: Removed 250+ lines of unused visual PDF editor frontend code
- **Error handling**: Improved error messages with troubleshooting guidance for Ollama, OpenAI, Anthropic

### Fixed
- PDF files now open in new browser tab with download controls instead of force-downloading
- Improved Ollama connection error messages with specific troubleshooting steps

## [Initial Release]

### Features
- RAG-based cover letter generation from job URL or text
- Multi-format document support (PDF, DOCX, Markdown, plain text)
- FastAPI backend with Vanilla JS frontend
- Ollama local inference
