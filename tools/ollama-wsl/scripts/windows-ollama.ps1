# Windows PowerShell 5.1; run as the Windows account that owns Ollama.
[CmdletBinding()]
param(
    [ValidateSet('check','configure','firewall','serve','restore')]
    [string]$Action = 'check',
    [ValidateRange(1,65535)][int]$Port = 11435,
    [string]$Distro = 'Ubuntu-24.04'
)
$ErrorActionPreference = 'Stop'
$ruleName = "Ollama-WSL-Bridge-$Port"
$backupDir = Join-Path $env:LOCALAPPDATA 'Ollama-WSL-Bridge'
$backupFile = Join-Path $backupDir 'environment-backup.json'

function Require-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Open PowerShell as Administrator using the same Windows account.'
    }
}
function Find-Ollama {
    $command = Get-Command ollama.exe -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    $candidate = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
    if (Test-Path $candidate) { return $candidate }
    throw 'Install Ollama from https://ollama.com/download/windows, then reopen PowerShell.'
}
function Get-WSLNetwork {
    $route = (& wsl.exe -d $Distro -- ip -4 route show default 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $route -notmatch '\bvia\s+([0-9.]+)') {
        throw "Cannot read the NAT gateway from $Distro. Check wsl --list --verbose."
    }
    $gateway = $Matches[1]
    $toHost = (& wsl.exe -d $Distro -- ip -4 route get $gateway 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $toHost -notmatch '\bsrc\s+([0-9.]+)') {
        throw 'Cannot determine the WSL source IPv4 address.'
    }
    $source = $Matches[1]
    if (-not (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
            Where-Object { $_.IPAddress -eq $gateway })) {
        throw 'The gateway is not a Windows local IPv4 address. Check VPN/custom routing.'
    }
    return @{ Gateway = $gateway; Source = $source }
}

switch ($Action) {
    'check' {
        $os = Get-CimInstance Win32_OperatingSystem
        Write-Host "OS: $($os.Caption); build $($os.BuildNumber); $($os.OSArchitecture)"
        if ([int]$os.BuildNumber -lt 19045) { Write-Warning 'Reference prerequisite: Windows 10 22H2 (build 19045) or newer.' }
        & wsl.exe --list --verbose
        if ($LASTEXITCODE -ne 0) { throw 'WSL listing failed.' }
        $exe = Find-Ollama
        & $exe --version
        Write-Host "User OLLAMA_HOST: $([Environment]::GetEnvironmentVariable('OLLAMA_HOST','User'))"
        $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
        if ($listeners.Count -eq 0) { Write-Host "No listener on TCP $Port."; break }
        $listeners | Select-Object LocalAddress,LocalPort,OwningProcess | Format-Table
        $version = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/version" -TimeoutSec 10
        Write-Host "API version: $($version.version)"
        $tags = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/tags" -TimeoutSec 10
        $tags.models | Select-Object name,size | Format-Table
        Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue |
            Select-Object Name,Enabled,Direction,Action | Format-Table
    }
    'configure' {
        $null = Find-Ollama
        if (-not (Test-Path $backupFile)) {
            New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
            @{ OLLAMA_HOST = [Environment]::GetEnvironmentVariable('OLLAMA_HOST','User') } |
                ConvertTo-Json | Set-Content -Path $backupFile -Encoding UTF8
        }
        [Environment]::SetEnvironmentVariable('OLLAMA_HOST',"0.0.0.0:$Port",'User')
        $env:OLLAMA_HOST = "0.0.0.0:$Port"
        Write-Host "Saved user OLLAMA_HOST=0.0.0.0:$Port"
        Write-Host 'Quit Ollama from the tray, then restart it. Existing server processes keep their old environment.'
    }
    'firewall' {
        Require-Admin
        $exe = Find-Ollama
        $network = Get-WSLNetwork
        # Replace only this package's named rule; refresh after a WSL IP change.
        Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue | Remove-NetFirewallRule
        New-NetFirewallRule -Name $ruleName -DisplayName "Ollama from WSL only ($Port)" `
            -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port `
            -LocalAddress $network.Gateway -RemoteAddress $network.Source `
            -Program $exe -Profile Any | Out-Null
        Write-Host "Allowed $($network.Source) -> $($network.Gateway):$Port for $exe"
    }
    'serve' {
        $exe = Find-Ollama
        if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) {
            throw "TCP $Port is occupied. Use check; do not start a second server on that port."
        }
        $env:OLLAMA_HOST = "0.0.0.0:$Port"
        Write-Host 'Foreground server: keep this window open; Ctrl+C stops it.'
        & $exe serve
        if ($LASTEXITCODE -ne 0) { throw "ollama serve exited with code $LASTEXITCODE" }
    }
    'restore' {
        Require-Admin
        if (-not (Test-Path $backupFile)) { throw 'No saved environment backup; nothing restored.' }
        $backup = Get-Content $backupFile -Raw | ConvertFrom-Json
        [Environment]::SetEnvironmentVariable('OLLAMA_HOST',$backup.OLLAMA_HOST,'User')
        if ($null -eq $backup.OLLAMA_HOST) { Remove-Item Env:OLLAMA_HOST -ErrorAction SilentlyContinue }
        else { $env:OLLAMA_HOST = $backup.OLLAMA_HOST }
        Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue | Remove-NetFirewallRule
        Write-Host "Restored the original user OLLAMA_HOST and removed $ruleName. Restart Ollama."
    }
}
