[CmdletBinding()]
param([string]$InstallRoot = 'D:\ad\codex\research-automation')
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
$catalog = Get-Content -Raw -LiteralPath (Join-Path $repoRoot 'integrations\research-automation-tools.json') | ConvertFrom-Json
$installed = [Collections.Generic.List[object]]::new()
$discovery = Join-Path $env:USERPROFILE '.codex\skills'
if ($env:CODEX_HOME) { $discovery = Join-Path $env:CODEX_HOME 'skills' }
[IO.Directory]::CreateDirectory($discovery) | Out-Null
foreach ($tool in $catalog.tools) {
    if ($tool.skill_name -notmatch '^research-[a-z0-9-]+$') { throw 'Invalid skill name' }
    $source = Join-Path $repoRoot $tool.skill_path
    if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant() -ne $tool.recipe_sha256) { throw "Modified adapter: $($tool.id)" }
    $target = [IO.Path]::GetFullPath((Join-Path $InstallRoot "skills\$($tool.skill_name)"))
    $entry = Join-Path $target 'SKILL.md'
    if (Test-Path -LiteralPath $entry) {
        if ((Get-FileHash -LiteralPath $entry -Algorithm SHA256).Hash.ToLowerInvariant() -ne $tool.recipe_sha256) { throw "Existing different skill preserved: $entry" }
    } else {
        [IO.Directory]::CreateDirectory($target) | Out-Null
        [IO.File]::WriteAllBytes($entry, [IO.File]::ReadAllBytes($source))
    }
    $link = Join-Path $discovery $tool.skill_name
    if (Test-Path -LiteralPath $link) {
        $existing = Get-Item -LiteralPath $link
        if ($existing.LinkType -ne 'Junction' -or [IO.Path]::GetFullPath([string]$existing.Target) -ne $target) { throw "Existing discovery entry preserved: $link" }
    } else { New-Item -ItemType Junction -Path $link -Target $target | Out-Null }
    if ((Get-FileHash -LiteralPath (Join-Path $link 'SKILL.md') -Algorithm SHA256).Hash.ToLowerInvariant() -ne $tool.recipe_sha256) { throw 'Discovery hash differs' }
    $sourceReceipt = Join-Path $InstallRoot "receipts\$($tool.id).json"
    $staged = $false
    if (Test-Path -LiteralPath $sourceReceipt) {
        $receipt = Get-Content -Raw -LiteralPath $sourceReceipt | ConvertFrom-Json
        $staged = $receipt.commit -eq $tool.commit -and (Test-Path -LiteralPath $receipt.source_root)
    }
    $installed.Add([ordered]@{id=$tool.id;skill=$tool.skill_name;repository=$tool.repository;commit=$tool.commit;sha256=$tool.recipe_sha256;entry=$link;canonical=$target;source_receipt_present=$staged;standalone_runtime_deployed=$false})
}
[IO.Directory]::CreateDirectory($InstallRoot) | Out-Null
$result = [ordered]@{schema_version='1.0';installed_at=[DateTimeOffset]::UtcNow.ToString('o');kind='Codex adapted skills';paid_calls=0;local_research_runtime_executed=$false;tools=$installed.ToArray()}
[IO.File]::WriteAllText((Join-Path $InstallRoot 'installation.json'), ($result | ConvertTo-Json -Depth 6), [Text.UTF8Encoding]::new($false))
Write-Output "Installed and hash-verified $($installed.Count) Codex skill entries. Standalone services are not deployed."
