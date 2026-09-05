# Lightweight install check for bug-bounty-ai-pipeline (Windows)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

Write-Host "== bug-bounty-ai-pipeline install check =="

Write-Host "1. Checking Python..."
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    Write-Host "   ERROR: python not found. Install Python 3.10+."
    exit 1
}
$ver = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
Write-Host "   OK: python ($ver)"

Write-Host "2. Checking uv..."
$uv = Get-Command uv -ErrorAction SilentlyContinue
if (-not $uv) {
    Write-Host "   ERROR: uv not found."
    Write-Host "   Install: https://docs.astral.sh/uv/getting-started/installation/"
    exit 1
}
Write-Host "   OK: $(uv --version)"

Write-Host "3. Portfolio config..."
if (-not (Test-Path "config/portfolio.yaml")) {
    if (Test-Path "config/portfolio.yaml.example") {
        Copy-Item "config/portfolio.yaml.example" "config/portfolio.yaml"
        Write-Host "   Created config/portfolio.yaml from example — edit before /portfolio discover."
    }
}
if (-not (Test-Path "config/.env.portfolio") -and -not (Test-Path ".env")) {
    if (Test-Path "config/.env.portfolio.example") {
        Copy-Item "config/.env.portfolio.example" "config/.env.portfolio"
        Write-Host "   Created config/.env.portfolio from example — add API keys before Phase 1."
    }
}

Write-Host "4. Smoke test..."
$env:PYTHONPATH = "."
try {
    uv run --with pytest python -m pytest tests/test_scaffold.py -q
} catch {
    Write-Host "   WARN: pytest smoke failed — check PYTHONPATH and Python version."
}

Write-Host ""
Write-Host "Done. Next steps:"
Write-Host "  1. Open this folder in Cursor"
Write-Host "  2. Copy config examples if not done: config/portfolio.yaml, config/.env.portfolio"
Write-Host "  3. Optional: npx skills add shenwell/ai-agent-skills --skill memo-session-skill -g -a cursor -y"
Write-Host "  4. Phase 1: /portfolio discover  |  Phase 2: /new <platform> <slug>"
