[CmdletBinding()]
param([string]$InstallRoot = 'D:\ad\lunwen', [string]$Distribution = 'Ubuntu')
$ErrorActionPreference = 'Stop'
$expected = [IO.Path]::GetFullPath('D:\ad\lunwen').TrimEnd('\')
$actual = [IO.Path]::GetFullPath($InstallRoot).TrimEnd('\')
if ($actual -ne $expected) { throw "All project components must be installed at D:\ad\lunwen; received $actual" }
if (-not (Test-Path -LiteralPath (Join-Path $actual 'scripts\bootstrap-d-drive.sh'))) { throw "Repository not found at $actual." }
$runtime = Join-Path $actual '.runtime'
@('pip-cache','huggingface','xdg-cache','xdg-data','tmp','matplotlib','paperqa','tooluniverse','docker-desktop','wsl') | ForEach-Object { New-Item -ItemType Directory -Force -Path (Join-Path $runtime $_) | Out-Null }
$wslList = (& wsl.exe --list --quiet) -join "`n"
if ($wslList -notmatch [regex]::Escape($Distribution)) { throw "Install/import '$Distribution' under D:\ad\lunwen\.runtime\wsl first." }
$wslExpected = [IO.Path]::GetFullPath((Join-Path $runtime 'wsl')).TrimEnd('\')
$record = Get-ChildItem 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Lxss' -ErrorAction SilentlyContinue | ForEach-Object { Get-ItemProperty $_.PSPath } | Where-Object { $_.DistributionName -eq $Distribution } | Select-Object -First 1
if ($null -eq $record -or -not $record.BasePath) { throw "Cannot verify WSL distribution location." }
$base = [string]$record.BasePath
if ($base.StartsWith('\\?\')) { $base = $base.Substring(4) }
$base = [IO.Path]::GetFullPath($base).TrimEnd('\')
if (-not ($base -eq $wslExpected -or $base.StartsWith($wslExpected + '\',[StringComparison]::OrdinalIgnoreCase))) { throw "WSL distribution is at '$base'; expected under '$wslExpected'." }
$dockerExpected = [IO.Path]::GetFullPath((Join-Path $runtime 'docker-desktop')).TrimEnd('\')
function Get-StringLeaf([object]$Value) {
  if ($null -eq $Value) { return }
  if ($Value -is [string]) { Write-Output $Value; return }
  if ($Value -is [Collections.IEnumerable] -and -not ($Value -is [string])) { foreach ($item in $Value) { Get-StringLeaf $item }; return }
  foreach ($property in $Value.PSObject.Properties) { Get-StringLeaf $property.Value }
}
$match = $null; $settingsFile = $null
@((Join-Path $env:APPDATA 'Docker\settings-store.json'),(Join-Path $env:APPDATA 'Docker\settings.json')) | Where-Object { Test-Path $_ } | ForEach-Object {
  $candidateFile = $_
  try { $settings = Get-Content $_ -Raw | ConvertFrom-Json } catch { return }
  foreach ($leaf in (Get-StringLeaf $settings)) {
    try { $candidate = [IO.Path]::GetFullPath($leaf).TrimEnd('\') } catch { continue }
    if ($candidate -eq $dockerExpected -or $candidate.StartsWith($dockerExpected + '\',[StringComparison]::OrdinalIgnoreCase)) { $script:match=$candidate; $script:settingsFile=$candidateFile; break }
  }
}
if ($null -eq $match) { throw "Set Docker Desktop Disk image location to $dockerExpected, apply/restart, then rerun." }
[ordered]@{schema_version='1.0';verified=$true;expected_root=$dockerExpected;configured_path=$match;settings_file=$settingsFile;confirmed_by=$env:USERNAME;confirmed_at=[DateTimeOffset]::UtcNow.ToString('o')} | ConvertTo-Json | Set-Content (Join-Path $runtime 'docker-location.json') -Encoding UTF8
$wslRoot = (& wsl.exe -d $Distribution -- wslpath -a $actual).Trim()
if ($wslRoot -ne '/mnt/d/ad/lunwen') { throw "WSL resolved repository as '$wslRoot'." }
& wsl.exe -d $Distribution --cd /mnt/d/ad/lunwen -- bash scripts/bootstrap-d-drive.sh
if ($LASTEXITCODE -ne 0) { throw "WSL bootstrap failed with exit code $LASTEXITCODE" }
Write-Host 'D-drive installation completed.'
