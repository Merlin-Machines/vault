param(
    [Parameter(Mandatory = $true)]
    [string]$Repo,
    [string]$Base = "main",
    [string]$Head = "",
    [string]$Title = "",
    [string]$BodyFile = "",
    [switch]$Draft
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not $Head) {
    $Head = (git branch --show-current).Trim()
    if (-not $Head) {
        throw "Could not determine current git branch. Pass -Head explicitly."
    }
}

$parts = $Repo.Split("/")
if ($parts.Length -ne 2) {
    throw "Repo must be in owner/name format."
}
$owner = $parts[0]
$name = $parts[1]

if (-not $Title) {
    $Title = "Update from $Head"
}

$body = "Automated PR created from local workflow."
if ($BodyFile) {
    if (-not (Test-Path -LiteralPath $BodyFile)) {
        throw "Body file not found: $BodyFile"
    }
    $body = Get-Content -LiteralPath $BodyFile -Raw
}

$token = $env:GITHUB_TOKEN
if (-not $token) {
    throw "Set GITHUB_TOKEN before running this script."
}

$headers = @{
    Authorization = "Bearer $token"
    Accept        = "application/vnd.github+json"
    "User-Agent"  = "vault-open-pr-script"
}

$existingUrl = "https://api.github.com/repos/$owner/$name/pulls?state=open&head=$owner`:$Head"
$existing = Invoke-RestMethod -Method Get -Uri $existingUrl -Headers $headers
if ($existing.Count -gt 0) {
    $pr = $existing[0]
    Write-Host "PR already exists: $($pr.html_url)"
    exit 0
}

$payload = @{
    title = $Title
    head  = $Head
    base  = $Base
    body  = $body
    draft = [bool]$Draft
} | ConvertTo-Json -Depth 6

$createUrl = "https://api.github.com/repos/$owner/$name/pulls"
$created = Invoke-RestMethod -Method Post -Uri $createUrl -Headers $headers -ContentType "application/json" -Body $payload
Write-Host "Opened PR: $($created.html_url)"
