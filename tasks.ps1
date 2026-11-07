<#
ASD_AGENT task runner (Windows PowerShell 5.1+). Run from the project root:

    .\tasks.ps1 help
    .\tasks.ps1 all          # db-health + test + verify + secrets  (what a reviewer runs)

No task calls Cohere or NVIDIA. All verification is cache-only and read-only on the database.
#>
param(
    [Parameter(Position = 0)][string]$Task = 'help',
    [Parameter(Position = 1)][string]$Arg = ''
)

$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
$Py = Join-Path $Root '.venv-embedding\Scripts\python.exe'
# Database instance. Defaults = the original machine; override to run an isolated second cluster.
$DbProject = if ($env:ASD_DB_PROJECT) { $env:ASD_DB_PROJECT } else { 'deployments' }
$DbVolume = if ($env:ASD_DB_VOLUME) { $env:ASD_DB_VOLUME } else { 'deployments_carobud_rag_data' }
$DbPort = if ($env:ASD_DB_PORT) { $env:ASD_DB_PORT } else { '5433' }
$Container = "$DbProject-rag-db-1"
$env:RAG_DB_VOLUME = $DbVolume
$env:RAG_DB_PORT = $DbPort
$Compose = Join-Path $Root 'deployments\compose.rag.yml'
$ComposeEnv = Join-Path $Root 'deployments\rag-db.env'
$Backups = Join-Path $Root 'backups'

# This machine has CURL_CA_BUNDLE pointing at a drive that no longer exists; it breaks pip/HTTPS.
Remove-Item Env:CURL_CA_BUNDLE -ErrorAction SilentlyContinue
$env:PYTHONPATH = $Root
$env:PYTHONIOENCODING = 'utf-8'
$env:TRANSFORMERS_VERBOSITY = 'error'   # only the tokenizer is used; silence the "PyTorch not found" notice

function Invoke-Checked([string]$Label, [scriptblock]$Block) {
    # Success is decided by the exit code only: in Windows PowerShell 5.1, harmless stderr
    # lines from native tools would otherwise become terminating errors.
    Write-Host "==> $Label" -ForegroundColor Cyan
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $Block 2>&1 | ForEach-Object { "$_" } | Write-Host
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
    }
    if ($code -ne 0) { throw "$Label failed (exit $code)" }
}

function Invoke-Quiet([scriptblock]$Block) {
    # Best-effort cleanup commands: output and stderr notices are discarded.
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & $Block 2>&1 | Out-Null } finally { $ErrorActionPreference = $previous }
}

function Test-Python {
    if (-not (Test-Path $Py)) { throw "Missing $Py. Run: .\tasks.ps1 setup" }
}

function Wait-DbHealthy {
    for ($i = 0; $i -lt 40; $i++) {
        $state = docker inspect -f '{{.State.Health.Status}}' $Container 2>$null
        if ($state -eq 'healthy') { return }
        Start-Sleep -Seconds 1
    }
    throw "Container $Container did not become healthy"
}

function Get-RowHashes([string]$Database) {
    $q = "select t, count(*), md5(string_agg(h, '' order by h)) from (" +
         "select 'collections' t, md5(row_to_json(x)::text) h from carobud_rag.collections x union all " +
         "select 'documents', md5(row_to_json(x)::text) from carobud_rag.documents x union all " +
         "select 'embedding_spaces', md5(row_to_json(x)::text) from carobud_rag.embedding_spaces x union all " +
         "select 'embeddings', md5(row_to_json(x)::text) from carobud_rag.embeddings x) s group by t order by t;"
    $rows = docker exec $Container psql -U postgres -d $Database -Atc $q
    if ($LASTEXITCODE -ne 0) { throw "psql failed on $Database" }
    return ($rows -join "`n")
}

function Test-DumpChecksum([string]$Path) {
    $sumFile = "$Path.sha256"
    if (-not (Test-Path $sumFile)) { throw "Missing checksum file $sumFile (copy it together with the dump)" }
    $expected = (Get-Content $sumFile -TotalCount 1).Split(' ')[0].Trim().ToLower()
    $actual = (Get-FileHash -Algorithm SHA256 $Path).Hash.ToLower()
    if ($actual -ne $expected) { throw "Checksum mismatch: $Path" }
}

function Get-NativeOutput([scriptblock]$Block) {
    # Runs a native command; returns stdout (stderr discarded) and leaves $LASTEXITCODE for the caller.
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { return (& $Block 2>$null) } finally { $ErrorActionPreference = $previous }
}

switch ($Task) {
    'help' {
        @'
Tasks:
  setup             Create .venv-embedding (Python 3.13) and install requirements.lock.txt
  db-up             Start the DB container; on a new machine create the volume + container (empty DB)
  db-bootstrap F    New machine: restore backup F (.dump + .sha256) into the EMPTY asd_rag; refuses if data exists
  env               Venv matches requirements.lock.txt (names normalized) + DB diagnosis by layer
  db-health         Check collection pins: 33 documents / 33 vectors / 1536 dims, read-only
  db-backup         pg_dump -Fc to backups/asd_rag_<time>.dump (+ .sha256)
  db-restore-check  Restore the newest backup into a new uniquely named DB, compare row hashes, drop only that DB
DB instance: ASD_DB_PROJECT (deployments), ASD_DB_VOLUME (deployments_carobud_rag_data), ASD_DB_PORT (5433).
  test              All 3 test suites; fails on any failure/skip or unexpected test count
  verify            4 cache-only verifiers (evidence/context, reader v2, reader v3, input guard)
  diag              Offline retrieval diagnostics (per dataset + unique questions)
  secrets           Scan git-tracked files for credentials
  pins              Fast check (no DB) that no hash-pinned file was edited; run before every commit
  hooks             Install a git pre-commit hook: staged secret scan + pins (blocks the commit on failure)
  all               env, pins, db-health, test, verify, secrets
Outputs go to reports/verification_runs/<name>_<time>/ (git-ignored). Historical reports are never modified.
'@ | Write-Host
    }
    'setup' {
        if (-not (Test-Path $Py)) {
            # Python 3.13 is required (tested 3.13.9). Order: $env:ASD_PYTHON, py launcher, python on PATH.
            $candidates = @()
            if ($env:ASD_PYTHON) { $candidates += , @($env:ASD_PYTHON) }
            $candidates += , @('py', '-3.13')
            $candidates += , @('python')
            $base = $null
            foreach ($c in $candidates) {
                $exe = $c[0]; $pre = @($c | Select-Object -Skip 1)
                $previous = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
                $ver = & $exe @pre -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
                $ErrorActionPreference = $previous
                if ($LASTEXITCODE -eq 0 -and $ver -eq '3.13') { $base = $c; break }
            }
            if (-not $base) { throw 'Python 3.13 not found. Install it or set $env:ASD_PYTHON to a python 3.13 executable.' }
            $exe = $base[0]; $pre = @($base | Select-Object -Skip 1)
            Invoke-Checked "create venv with $($base -join ' ')" { & $exe @pre -m venv (Join-Path $Root '.venv-embedding') }
        }
        Invoke-Checked 'install locked dependencies' { & $Py -m pip install --disable-pip-version-check -r (Join-Path $Root 'requirements.lock.txt') }
    }
    'db-up' {
        $exists = Get-NativeOutput { docker ps -a --filter "name=^$Container$" --format '{{.Names}}' }
        if ($exists) {
            Invoke-Checked "docker start $Container" { docker start $Container | Out-Null }
        } else {
            if (-not (Test-Path $ComposeEnv)) { throw "Create $ComposeEnv from deployments\rag-db.env.example first" }
            $null = Get-NativeOutput { docker volume inspect $DbVolume }
            if ($LASTEXITCODE -ne 0) {
                # The compose volume is external (so `down` can never delete data): create it explicitly.
                Invoke-Checked "create volume $DbVolume" { docker volume create --label asd_agent=rag-db $DbVolume | Out-Null }
                Write-Host "New EMPTY volume $DbVolume. Next: .\tasks.ps1 db-bootstrap <backup.dump>" -ForegroundColor Yellow
            }
            Invoke-Checked "docker compose up (project $DbProject)" { docker compose -p $DbProject -f $Compose --env-file $ComposeEnv up -d }
        }
        Wait-DbHealthy
        Write-Host "PostgreSQL healthy on 127.0.0.1:$DbPort ($Container)" -ForegroundColor Green
    }
    'db-bootstrap' {
        if (-not $Arg) { throw 'Usage: .\tasks.ps1 db-bootstrap <path\to\asd_rag_<time>.dump>  (copy the .sha256 file next to it)' }
        $dump = (Resolve-Path $Arg).Path
        Test-DumpChecksum $dump
        Wait-DbHealthy
        # Never overwrite: the target must not contain the RAG schema yet.
        $has = Get-NativeOutput { docker exec $Container psql -U postgres -d asd_rag -Atc "select count(*) from pg_namespace where nspname='carobud_rag'" }
        if ($LASTEXITCODE -ne 0) { throw "Cannot query asd_rag in $Container" }
        if ("$has".Trim() -ne '0') { throw "asd_rag in $Container already contains schema carobud_rag; refusing to restore over it" }
        $tmpFile = "/tmp/asd_bootstrap_$([guid]::NewGuid().ToString('N')).dump"
        try {
            Invoke-Checked 'copy dump into container' { docker cp $dump "${Container}:$tmpFile" }
            Invoke-Checked 'pg_restore into asd_rag' { docker exec $Container pg_restore -U postgres -d asd_rag --no-owner $tmpFile }
        } finally {
            Invoke-Quiet { docker exec $Container rm -f $tmpFile }
        }
        Write-Host (Get-RowHashes 'asd_rag')
        Write-Host "Restored. Next: create deployments\database.env for port $DbPort, then .\tasks.ps1 all" -ForegroundColor Green
    }
    'env' {
        Test-Python
        Invoke-Checked 'environment vs lockfile' { & $Py -B (Join-Path $Root 'scripts\dev\check_env.py') }
        Invoke-Checked 'database diagnosis' { & $Py -B (Join-Path $Root 'scripts\dev\env_diagnose.py') }
    }
    'db-health' {
        Test-Python
        Invoke-Checked 'retriever health' { & $Py -B -c "from rag.retriever import PostgresRetriever as R; import json; print(json.dumps(R().health()))" }
    }
    'db-backup' {
        New-Item -ItemType Directory -Force $Backups | Out-Null
        $name = 'asd_rag_' + (Get-Date -Format 'yyyyMMdd_HHmmss') + '.dump'
        Invoke-Checked 'pg_dump' { docker exec $Container pg_dump -U postgres -d asd_rag -Fc -f "/tmp/$name" }
        Invoke-Checked 'copy dump' { docker cp "${Container}:/tmp/$name" (Join-Path $Backups $name) }
        Invoke-Quiet { docker exec $Container rm "/tmp/$name" }
        $hash = (Get-FileHash -Algorithm SHA256 (Join-Path $Backups $name)).Hash.ToLower()
        Set-Content -Encoding ascii -Path (Join-Path $Backups "$name.sha256") -Value "$hash *$name"
        Write-Host "Backup: backups\$name  sha256=$hash" -ForegroundColor Green
    }
    'db-restore-check' {
        $dump = Get-ChildItem $Backups -Filter 'asd_rag_*.dump' | Sort-Object Name | Select-Object -Last 1
        if (-not $dump) { throw 'No backup found. Run: .\tasks.ps1 db-backup' }
        Test-DumpChecksum $dump.FullName
        # Unique per run: never touches a database or file this run did not create.
        $token = [guid]::NewGuid().ToString('N')
        $tmp = "asd_restore_check_$token"
        $tmpFile = "/tmp/asd_restore_check_$token.dump"
        $created = $false
        try {
            Invoke-Checked 'copy dump into container' { docker cp $dump.FullName "${Container}:$tmpFile" }
            Invoke-Checked "createdb $tmp" { docker exec $Container createdb -U postgres $tmp }
            $created = $true
            Invoke-Checked 'pg_restore' { docker exec $Container pg_restore -U postgres -d $tmp --no-owner $tmpFile }
            $live = Get-RowHashes 'asd_rag'
            $restored = Get-RowHashes $tmp
            Write-Host $live
            if ($live -ne $restored) { throw 'Restored database differs from live database' }
            Write-Host "RESTORE CHECK PASS: $($dump.Name) reproduces every row of asd_rag" -ForegroundColor Green
        } finally {
            if ($created) { Invoke-Quiet { docker exec $Container dropdb -U postgres $tmp } }
            Invoke-Quiet { docker exec $Container rm -f $tmpFile }
        }
    }
    'test' {
        Test-Python
        Invoke-Checked 'all test suites' { & $Py -B (Join-Path $Root 'scripts\dev\run_all_tests.py') }
    }
    'verify' {
        Test-Python
        foreach ($v in 'verify_evidence_context', 'verify_semantic_reader', 'verify_reader_v3', 'verify_guarded_pipeline', 'verify_answer_layer') {
            Invoke-Checked $v { & $Py -B (Join-Path $Root "scripts\evaluation\$v.py") | Select-String -Pattern 'AUDIT_DIR|VERIFIED|"status"' }
        }
        Write-Host 'All verifiers passed (cache-only, no provider calls).' -ForegroundColor Green
    }
    'diag' {
        Test-Python
        Invoke-Checked 'retrieval diagnostics' { & $Py -B (Join-Path $Root 'scripts\evaluation\diagnose_retrieval_offline.py') }
    }
    'secrets' {
        Test-Python
        Invoke-Checked 'secret scan' { & $Py -B (Join-Path $Root 'scripts\dev\secret_scan.py') }
    }
    'pins' {
        Test-Python
        Invoke-Checked 'hash pins' { & $Py -B (Join-Path $Root 'scripts\dev\check_pins.py') }
    }
    'hooks' {
        Test-Python
        $hook = Join-Path $Root '.git\hooks\pre-commit'
        $body = @'
#!/bin/sh
# Installed by tasks.ps1 hooks. Blocks commits that stage a credential or edit a hash-pinned file.
PY=".venv-embedding/Scripts/python.exe"
"$PY" -B scripts/dev/secret_scan.py --staged || exit 1
"$PY" -B scripts/dev/check_pins.py || exit 1
'@
        [IO.File]::WriteAllText($hook, $body.Replace("`r`n", "`n"), (New-Object Text.UTF8Encoding $false))
        Write-Host "Installed $hook" -ForegroundColor Green
    }
    'all' {
        foreach ($t in 'env', 'pins', 'db-health', 'test', 'verify', 'secrets') {
            & $PSCommandPath $t
            if (-not $?) { throw "Task $t failed" }
        }
        Write-Host 'ALL CHECKS PASSED' -ForegroundColor Green
    }
    default { throw "Unknown task '$Task'. Run .\tasks.ps1 help" }
}
