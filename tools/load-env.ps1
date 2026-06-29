param(
  [string]$Path = ".env.local"
)

function Load-EnvFile {
  param([string]$EnvPath)

  if (!(Test-Path $EnvPath)) {
    Write-Host "No $EnvPath found; skipping local env load."
    return
  }

  Get-Content $EnvPath | ForEach-Object {
    $line = $_.Trim()

    if (!$line -or $line.StartsWith("#")) {
      return
    }

    $parts = $line -split "=", 2
    if ($parts.Count -ne 2) {
      return
    }

    $name = $parts[0].Trim()
    $value = $parts[1].Trim()

    if (
      ($value.StartsWith('"') -and $value.EndsWith('"')) -or
      ($value.StartsWith("'") -and $value.EndsWith("'"))
    ) {
      $value = $value.Substring(1, $value.Length - 2)
    }

    Set-Item -Path "Env:$name" -Value $value
    Write-Host "Loaded $name"
  }
}

if (!(Test-Path $Path)) {
  Write-Host "No $Path found; skipping local env load."
  return
}

$first = Get-Content $Path | Where-Object {
  $_.Trim() -and -not $_.Trim().StartsWith("#")
} | Select-Object -First 1

if ($first -and $first.Trim().StartsWith("ENV_FILE=")) {
  $target = ($first -split "=", 2)[1].Trim()
  Load-EnvFile $target
} else {
  Load-EnvFile $Path
}