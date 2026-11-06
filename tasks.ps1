<#
ASD_AGENT task runner (Windows PowerShell 5.1+). Run from the project root:

    .\tasks.ps1 help
    .\tasks.ps1 all          # db-health + test + verify + secrets  (what a reviewer runs)

No task calls Cohere or NVIDIA. All verification is cache-only and read-only on the database.
#>
param([Parameter(Position = 0)][string]$Task = 'help')

$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
$Py = Join-Path $Root '.venv-embedding\Scripts\python.exe'
$Container = 'deployments-rag-db-1'
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

switch ($Task) {
    'help' {
        @'
Tasks:
  setup             Create .venv-embedding (Python 3.13) and install requirements.lock.txt
  db-up             Start PostgreSQL+pgvector (existing container, else deployments/compose.rag.yml)
  db-health         Check collection pins: 33 documents / 33 vectors / 1536 dims, read-only
  db-backup         pg_dump -Fc to backups/asd_rag_<time>.dump (+ .sha256)
  db-restore-check  Restore the newest backup into a temporary DB, compare row hashes, drop it
  test              All 3 test suites; fails on any failure/skip or unexpected test count
  verify            4 cache-only verifiers (evidence/context, reader v2, reader v3, input guard)
  diag              Offline retrieval diagnostics (per dataset + unique questions)
  secrets           Scan git-tracked files for credentials
  pins              Fast check (no DB) that no hash-pinned file was edited; run before every commit
  all               pins, db-health, test, verify, secrets
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
        $exists = docker ps -a --filter "name=^$Container$" --format '{{.Names}}'
        if ($exists) {
            Invoke-Checked "docker start $Container" { docker start $Container | Out-Null }
        } else {
            if (-not (Test-Path $ComposeEnv)) { throw "Create $ComposeEnv from deployments\rag-db.env.example first" }
            Invoke-Checked 'docker compose up' { docker compose -f $Compose --env-file $ComposeEnv up -d }
        }
        Wait-DbHealthy
        Write-Host "PostgreSQL healthy on 127.0.0.1:5433" -ForegroundColor Green
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
        $expected = (Get-Content (Join-Path $Backups "$($dump.Name).sha256")).Split(' ')[0]
        if ((Get-FileHash -Algorithm SHA256 $dump.FullName).Hash.ToLower() -ne $expected) { throw "Checksum mismatch: $($dump.Name)" }
        $tmp = 'asd_rag_restore_check'
        try {
            Invoke-Checked 'copy dump into container' { docker cp $dump.FullName "${Container}:/tmp/$($dump.Name)" }
            Invoke-Quiet { docker exec $Container dropdb -U postgres --if-exists $tmp }
            Invoke-Checked 'createdb' { docker exec $Container createdb -U postgres $tmp }
            Invoke-Checked 'pg_restore' { docker exec $Container pg_restore -U postgres -d $tmp --no-owner "/tmp/$($dump.Name)" }
            $live = Get-RowHashes 'asd_rag'
            $restored = Get-RowHashes $tmp
            Write-Host $live
            if ($live -ne $restored) { throw 'Restored database differs from live database' }
            Write-Host "RESTORE CHECK PASS: $($dump.Name) reproduces every row of asd_rag" -ForegroundColor Green
        } finally {
            Invoke-Quiet { docker exec $Container dropdb -U postgres --if-exists $tmp }
            Invoke-Quiet { docker exec $Container rm -f "/tmp/$($dump.Name)" }
        }
    }
    'test' {
        Test-Python
        Invoke-Checked 'all test suites' { & $Py -B (Join-Path $Root 'scripts\dev\run_all_tests.py') }
    }
    'verify' {
        Test-Python
        foreach ($v in 'verify_evidence_context', 'verify_semantic_reader', 'verify_reader_v3', 'verify_guarded_pipeline') {
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
    'all' {
        foreach ($t in 'pins', 'db-health', 'test', 'verify', 'secrets') {
            & $PSCommandPath $t
            if (-not $?) { throw "Task $t failed" }
        }
        Write-Host 'ALL CHECKS PASSED' -ForegroundColor Green
    }
    default { throw "Unknown task '$Task'. Run .\tasks.ps1 help" }
}
