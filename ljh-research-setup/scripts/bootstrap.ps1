param(
    [string]$Python,
    [string]$RuntimeDirectory = (Join-Path $env:LOCALAPPDATA 'LJHResearch'),
    [string]$InstallerUrl,
    [string]$InstallerSha256,
    [switch]$Apply,
    [switch]$Papers
)
$ErrorActionPreference = 'Stop'
$interpreterPath = $Python
if (-not $interpreterPath) {
    $candidate = Get-Command python -ErrorAction SilentlyContinue
    if ($candidate) { $interpreterPath = $candidate.Source }
}
if ($interpreterPath) {
    try {
        $verifiedPath = & $interpreterPath -I -c 'import sys; assert sys.version_info >= (3,11); print(sys.executable)' 2>$null
        if ($LASTEXITCODE -ne 0) { $interpreterPath = $null } else { $interpreterPath = [string]$verifiedPath }
    } catch { $interpreterPath = $null }
}
$runtimePath = [System.IO.Path]::GetFullPath($RuntimeDirectory)
$installScript = Join-Path $PSScriptRoot 'install_runtime.py'
if (-not $interpreterPath) {
    @{bundle=(Split-Path -Parent $PSScriptRoot); runtime=$runtimePath; python=$null; installer=$InstallerUrl; apply=[bool]$Apply; scope='user'} | ConvertTo-Json
    if (-not $Apply) { return }
    if (-not $InstallerUrl) { throw 'Python unavailable: provide an officially verified -InstallerUrl, then review the plan before -Apply' }
    $downloadUri = [uri]$InstallerUrl
    if ($downloadUri.Scheme -ne 'https' -or $downloadUri.Host -notin @('www.python.org','python.org') -or -not $downloadUri.AbsolutePath.EndsWith('.exe')) { throw 'Only an official Python HTTPS installer is accepted' }
    New-Item -ItemType Directory -Path $runtimePath -Force | Out-Null
    $installerPath = Join-Path $runtimePath 'python-installer.exe'
    Invoke-WebRequest -Uri $downloadUri -OutFile $installerPath
    if ($InstallerSha256 -and (Get-FileHash -LiteralPath $installerPath -Algorithm SHA256).Hash -ne $InstallerSha256) { throw 'Installer hash mismatch' }
    $signature = Get-AuthenticodeSignature -LiteralPath $installerPath
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Python Software Foundation') { throw 'Python installer signature is not valid' }
    $pythonTarget = Join-Path $runtimePath 'python'
    $process = Start-Process -FilePath $installerPath -ArgumentList @('/quiet','InstallAllUsers=0','PrependPath=0','Include_launcher=0','Include_pip=1',('TargetDir="' + $pythonTarget + '"')) -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -notin @(0,3010)) { throw ('Python installation failed: ' + $process.ExitCode) }
    $interpreterPath = Join-Path $pythonTarget 'python.exe'
}
$installArguments = @($installScript,'--runtime-dir',$runtimePath)
if ($Apply) { $installArguments += '--apply' }
if ($Papers) { $installArguments += '--papers' }
& $interpreterPath -I @installArguments
if ($LASTEXITCODE -ne 0) { throw 'Runtime installation or plan failed; inspect the reported error' }
