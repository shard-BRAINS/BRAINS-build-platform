# install.ps1 — install BRAINS Build Platform into ~/.claude/
# Run from c:\BRAINS_Build_Platform\

$ErrorActionPreference = "Stop"

$ClaudeHome = "$env:USERPROFILE\.claude"
$SkillsTarget = "$ClaudeHome\skills"
$AgentsTarget = "$ClaudeHome\agents\build"

Write-Output "Installing BRAINS Build Platform..."

# 1. Verify the Python package is installed editable (or install it now)
$pkg = pip show build-platform 2>$null
if (-not $pkg) {
    Write-Output "Installing build_platform Python package (editable)..."
    pip install -e ".[dev]"
}

# 2. Copy skills
if (-not (Test-Path $SkillsTarget)) { New-Item -ItemType Directory -Path $SkillsTarget -Force | Out-Null }
Get-ChildItem -Directory .\skills | ForEach-Object {
    $dest = Join-Path $SkillsTarget $_.Name
    if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
    Copy-Item -Recurse $_.FullName $dest
    Write-Output "  installed skill: $($_.Name)"
}

# 3. Copy agents
if (-not (Test-Path $AgentsTarget)) { New-Item -ItemType Directory -Path $AgentsTarget -Force | Out-Null }
Get-ChildItem -File .\agents\*.md | ForEach-Object {
    $dest = Join-Path $AgentsTarget $_.Name
    Copy-Item -Force $_.FullName $dest
    Write-Output "  installed agent: $($_.Name)"
}

Write-Output ""
Write-Output "Done. Next steps:"
Write-Output "  1. ollama pull qwen2.5-coder:7b"
Write-Output "  2. ollama pull llama3.2:3b"
Write-Output "  3. cd to a project directory and run /build-init in Claude Code"
