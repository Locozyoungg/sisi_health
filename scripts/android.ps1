# SISI Android build entry: sets JAVA_HOME/ANDROID_HOME for portable tools and
# forwards args to the Gradle wrapper. Usage: .\scripts\android.ps1 <gradle tasks>
param([Parameter(ValueFromRemainingArguments = $true)][string[]]$GradleArgs)

$ErrorActionPreference = "Stop"
$Tools = "E:\Projects\sisi_health\.tools"
$env:JAVA_HOME = Join-Path $Tools "jdk17"
$env:ANDROID_HOME = Join-Path $Tools "android-sdk"
$env:ANDROID_SDK_ROOT = $env:ANDROID_HOME
# Gradle caches live on E: — C: had <1 GB free (moved 2026-10-14, user-approved).
$env:GRADLE_USER_HOME = Join-Path $Tools "gradle-home"

Push-Location "E:\Projects\sisi_health\mobile"
try {
    & .\gradlew.bat @GradleArgs --console=plain
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally {
    Pop-Location
}
