# Creates NOVA's sandbox: an isolated WSL2 Ubuntu distro named "nova" (Phase 130).
#
# What the box is (see backend/eva/shell/sandbox_terminal.py):
#   - a Linux user "nova" with no sudo and no password, workspace /home/nova/workspace
#   - cannot see C: or D: (automount is off) and cannot launch Windows programs (interop off)
#   - sees exactly one Windows folder, $SharePath, as /mnt/share
#   - has internet, but an nftables rule written by root rejects private/LAN ranges
#     (DNS stays allowed), so it cannot reach this PC's services or the home network
#
# Run from an ADMINISTRATOR PowerShell:   .\scripts\setup_nova_box.ps1
# The first run may only install WSL itself and ask for a reboot; run it again afterwards.
# Safe to re-run: every step checks before it changes anything.
#
# STATUS: written without WSL available on the author's machine, so it has NOT been run
# end to end. The verification at the end prints PASS/FAIL per property; trust that, not this header.

param([string]$SharePath = "")

$ErrorActionPreference = "Stop"
$Distro = "nova"
$Repo = Split-Path -Parent $PSScriptRoot

function Step($text) { Write-Host "`n==> $text" -ForegroundColor Cyan }
function Fail($text) { Write-Host "FAILED: $text" -ForegroundColor Red; exit 1 }

# wsl.exe prints UTF-16; strip the NULs so -match and parsing work.
function Wsl-Text { (& wsl.exe @args 2>&1 | Out-String) -replace "`0", "" }

if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Fail "Open PowerShell as Administrator and run this again (installing WSL needs elevation)."
}

# The one Windows folder the box may see. Must match EVA_SANDBOX_SHARE (written below when not the default).
if (-not $SharePath) {
    $SharePath = if (Test-Path "D:\") { "D:\nova-share" } else { Join-Path $env:USERPROFILE "nova-share" }
}
New-Item -ItemType Directory -Force -Path $SharePath | Out-Null

Step "1/5 WSL"
$status = Wsl-Text --status
if ($LASTEXITCODE -ne 0 -or $status -match "not installed") {
    Write-Host "Installing the WSL platform (no distro yet)..."
    & wsl.exe --install --no-distribution
    Write-Host "`nWSL is installed. REBOOT Windows, then run this script again." -ForegroundColor Yellow
    exit 0
}
& wsl.exe --update | Out-Null

Step "2/5 the 'nova' distro"
$have = (Wsl-Text -l -q) -split "`r?`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ }
if ($have -contains $Distro) {
    Write-Host "Distro '$Distro' already exists; reusing it."
} else {
    Write-Host "Installing Ubuntu 24.04 as '$Distro' (about 1 GB download)..."
    & wsl.exe --install Ubuntu-24.04 --name $Distro --no-launch
    if ($LASTEXITCODE -ne 0) {
        Fail "Could not install a distro named '$Distro'. Needs WSL 2.4.4+ (run 'wsl --update'). Manual fallback: install Ubuntu-24.04, then 'wsl --export' and 'wsl --import $Distro' it."
    }
}

Step "3/5 configure the box (as root)"
$fstabHost = $SharePath -replace " ", "\040"
$setup = @'
set -e
id nova >/dev/null 2>&1 || useradd -m -s /bin/bash nova
passwd -l nova >/dev/null 2>&1 || true
mkdir -p /home/nova/workspace /mnt/share /mnt/c /mnt/d
chown -R nova:nova /home/nova
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y nftables curl ca-certificates git python3
cat > /etc/nova-firewall.nft <<'NFT'
flush ruleset
table inet nova_fw {
  chain output {
    type filter hook output priority 0; policy accept;
    oifname "lo" accept
    udp dport 53 accept
    tcp dport 53 accept
    ip daddr { 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 169.254.0.0/16, 100.64.0.0/10 } reject
    ip6 daddr { fc00::/7, fe80::/10 } reject
  }
}
NFT
chown root:root /etc/nova-firewall.nft
chmod 644 /etc/nova-firewall.nft
cat > /etc/wsl.conf <<'CONF'
[automount]
enabled=false
mountFsTab=true
[interop]
enabled=false
appendWindowsPath=false
[user]
default=nova
[boot]
command=nft -f /etc/nova-firewall.nft
CONF
grep -q ' /mnt/share ' /etc/fstab || echo '__SHARE__ /mnt/share drvfs metadata,uid=1000,gid=1000,umask=022 0 0' >> /etc/fstab
'@
$setup = ($setup -replace "__SHARE__", $fstabHost) -replace "`r`n", "`n"
$b64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($setup))
& wsl.exe -d $Distro -u root --exec bash -c "echo $b64 | base64 -d | bash"
if ($LASTEXITCODE -ne 0) { Fail "Configuring the box failed (see output above). Nothing outside the distro was changed." }

Step "4/5 restart the box so wsl.conf takes effect"
& wsl.exe --terminate $Distro | Out-Null
Start-Sleep -Seconds 3

Step "5/5 verify (runs as the 'nova' user, the way NOVA runs commands)"
$checks = @(
    @{ Name = "runs as user nova";                  Cmd = 'test "$(whoami)" = nova' },
    @{ Name = "cannot see C: (empty mount point)";  Cmd = 'test -z "$(ls -A /mnt/c 2>/dev/null)"' },
    @{ Name = "cannot see D: (empty mount point)";  Cmd = 'test -z "$(ls -A /mnt/d 2>/dev/null)"' },
    @{ Name = "no sudo for nova";                   Cmd = '! sudo -n true 2>/dev/null' },
    @{ Name = "cannot launch Windows programs";     Cmd = '! command -v cmd.exe >/dev/null 2>&1' },
    @{ Name = "can write the share (/mnt/share)";   Cmd = 'touch /mnt/share/.nova_check && rm /mnt/share/.nova_check' },
    @{ Name = "internet works";                     Cmd = 'curl -s -m 10 -o /dev/null https://example.com' },
    @{ Name = "LAN/private ranges are blocked";     Cmd = '! curl -s -m 4 -o /dev/null http://192.168.0.1' },
    @{ Name = "firewall file not writable by nova"; Cmd = '! test -w /etc/nova-firewall.nft' }
)
$bad = 0
foreach ($check in $checks) {
    $encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($check.Cmd))
    & wsl.exe -d $Distro -u nova --exec bash -c "echo $encoded | base64 -d | bash" 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { Write-Host ("  PASS  " + $check.Name) -ForegroundColor Green }
    else { Write-Host ("  FAIL  " + $check.Name) -ForegroundColor Red; $bad++ }
}

# Tell NOVA where the share is when it is not the default D:\nova-share.
if ($SharePath -ne "D:\nova-share") {
    $envFile = Join-Path $Repo ".env.local"
    $line = "EVA_SANDBOX_SHARE=$SharePath"
    $existing = if (Test-Path $envFile) { Get-Content $envFile -Raw } else { "" }
    if ($existing -notmatch "(?m)^EVA_SANDBOX_SHARE=") { Add-Content -Path $envFile -Value $line }
    Write-Host "`nShare folder: $SharePath (saved to .env.local as EVA_SANDBOX_SHARE)"
}

if ($bad -eq 0) { Write-Host "`nThe NOVA box is ready. Restart NOVA, then try: use your terminal to run uname -a" -ForegroundColor Green }
else { Write-Host "`n$bad check(s) failed. Do not rely on the box's isolation until they pass." -ForegroundColor Yellow; exit 2 }
