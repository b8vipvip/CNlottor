param(
    [string]$HostAddress = "0.0.0.0",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

function Test-CompatiblePython {
    param(
        [string]$Command,
        [string[]]$PrefixArguments
    )

    if (-not (Get-Command $Command -ErrorAction SilentlyContinue)) {
        return $false
    }

    try {
        & $Command @PrefixArguments -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" *> $null
        return $LASTEXITCODE -eq 0
    }
    catch {
        return $false
    }
}

function Find-CompatiblePython {
    $Candidates = @(
        @{ Command = "py"; Arguments = @("-3.12") },
        @{ Command = "py"; Arguments = @("-3.11") },
        @{ Command = "py"; Arguments = @("-3.10") },
        @{ Command = "python"; Arguments = @() }
    )

    foreach ($Candidate in $Candidates) {
        if (Test-CompatiblePython -Command $Candidate.Command -PrefixArguments $Candidate.Arguments) {
            return [PSCustomObject]@{
                Command = $Candidate.Command
                Arguments = [string[]]$Candidate.Arguments
            }
        }
    }

    return $null
}

# The same launcher works from the source tree (tools/windows) and from the
# packaged Windows bundle root.
$Root = $PSScriptRoot
$SourceRootCandidate = Join-Path $PSScriptRoot "..\.."
if (-not (Test-Path (Join-Path $Root "pyproject.toml")) -and
    (Test-Path (Join-Path $SourceRootCandidate "pyproject.toml"))) {
    $Root = (Resolve-Path $SourceRootCandidate).Path
}

Set-Location $Root

$Venv = Join-Path $Root ".venv"
$Python = Join-Path $Venv "Scripts\python.exe"
$DataDirectory = Join-Path $Root "data"
$ModelsDirectory = Join-Path $Root "artifacts\models"
$Database = Join-Path $DataDirectory "cnlottor.db"

New-Item -ItemType Directory -Force -Path $DataDirectory | Out-Null
New-Item -ItemType Directory -Force -Path $ModelsDirectory | Out-Null

if (-not (Test-Path $Python)) {
    $Launcher = Find-CompatiblePython
    if ($null -eq $Launcher) {
        throw "未找到兼容的 Python。请安装 Python 3.12、3.11 或 3.10，并勾选 Python Launcher/添加到 PATH。"
    }

    Write-Host "[CNlottor] 正在使用兼容的 Python 创建虚拟环境……"
    $LauncherCommand = [string]$Launcher.Command
    $LauncherArguments = [string[]]$Launcher.Arguments
    & $LauncherCommand @LauncherArguments -m venv $Venv
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $Python)) {
        throw "创建虚拟环境失败。"
    }
}

$SourceProject = Test-Path (Join-Path $Root "pyproject.toml")
if ($SourceProject) {
    $Marker = Join-Path $Venv ".cnlottor-source-dependencies-installed"
    if (-not (Test-Path $Marker)) {
        Write-Host "[CNlottor] 首次启动：正在安装源码版依赖（包含 PyTorch，可能需要较长时间）……"
        & $Python -m pip install --upgrade pip setuptools wheel
        & $Python -m pip install -e ".[all]"
        if ($LASTEXITCODE -ne 0) {
            throw "安装 CNlottor 源码依赖失败。"
        }
        New-Item -ItemType File -Force -Path $Marker | Out-Null
    }
}
else {
    $Wheel = Get-ChildItem (Join-Path $Root "server\cnlottor-*.whl") -ErrorAction Stop |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($null -eq $Wheel) {
        throw "发布包中没有找到 server\cnlottor-*.whl。"
    }

    $MarkerName = ".{0}.installed" -f $Wheel.BaseName
    $Marker = Join-Path $Venv $MarkerName
    if (-not (Test-Path $Marker)) {
        Write-Host "[CNlottor] 首次启动：正在安装服务端依赖（包含 PyTorch，可能需要较长时间）……"
        & $Python -m pip install --upgrade pip setuptools wheel
        $WheelWithExtras = "{0}[all]" -f $Wheel.FullName
        & $Python -m pip install $WheelWithExtras
        if ($LASTEXITCODE -ne 0) {
            throw "安装 CNlottor 服务端失败。"
        }
        Get-ChildItem $Venv -Filter ".cnlottor-*.installed" -ErrorAction SilentlyContinue |
            Remove-Item -Force -ErrorAction SilentlyContinue
        New-Item -ItemType File -Force -Path $Marker | Out-Null
    }
}

$Version = & $Python -c "import cnlottor; print(cnlottor.__version__)"
Write-Host "[CNlottor] 版本：$Version"
Write-Host "[CNlottor] 数据库：$Database"
Write-Host "[CNlottor] 模型目录：$ModelsDirectory"
Write-Host "[CNlottor] 本机客户端地址：http://127.0.0.1:$Port"
if ($HostAddress -eq "0.0.0.0") {
    Write-Host "[CNlottor] 已允许局域网访问；Android 客户端请填写本机局域网 IP 和端口 $Port。"
}
Write-Host "[CNlottor] 按 Ctrl+C 可停止服务。"

& $Python -m cnlottor.cli serve `
    --database $Database `
    --models $ModelsDirectory `
    --host $HostAddress `
    --port $Port
