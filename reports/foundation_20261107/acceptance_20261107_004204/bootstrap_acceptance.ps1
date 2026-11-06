# New-machine acceptance: clean clone + fresh venv + ISOLATED PostgreSQL cluster
# (own compose project, own NEW volume, port 5435, different password) restored from a transferred backup.
# Touches nothing of the original DB except read-only row hashes before/after.
param([string]$Clone, [string]$Source = 'D:\AI4LIFE\ASD_AGENT', [string]$Dump = 'asd_rag_20261107_000554.dump')
$ErrorActionPreference = 'Stop'
function Step($t) { Write-Host ""; Write-Host "######## $t" }
function Live-Hashes { docker exec deployments-rag-db-1 psql -U postgres -d asd_rag -Atc "select t, count(*), md5(string_agg(h, '' order by h)) from (select 'collections' t, md5(row_to_json(x)::text) h from carobud_rag.collections x union all select 'documents', md5(row_to_json(x)::text) from carobud_rag.documents x union all select 'embedding_spaces', md5(row_to_json(x)::text) from carobud_rag.embedding_spaces x union all select 'embeddings', md5(row_to_json(x)::text) from carobud_rag.embeddings x) s group by t order by t;" }

$env:ASD_DB_PROJECT = 'asdboot'; $env:ASD_DB_VOLUME = 'asdboot_rag_data'; $env:ASD_DB_PORT = '5435'
$c = 'asdboot-rag-db-1'
Step "precondition: isolated test resources do not exist yet"
$prevE = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
docker volume inspect $env:ASD_DB_VOLUME 2>$null | Out-Null; $volExists = ($LASTEXITCODE -eq 0)
docker inspect $c 2>$null | Out-Null; $ctExists = ($LASTEXITCODE -eq 0)
$ErrorActionPreference = $prevE
if ($volExists -or $ctExists) { throw 'Test volume/container already exists; refusing to continue' }
"volume $($env:ASD_DB_VOLUME) exists: $volExists ; container $c exists: $ctExists"
$liveBefore = (Live-Hashes) -join "`n"
"original DB row hashes (before):"; $liveBefore

try {
    Step "clean clone"
    if (Test-Path $Clone) { Remove-Item -Recurse -Force $Clone }
    git -c core.longpaths=true clone -q $Source $Clone
    Set-Location $Clone
    git config core.longpaths true
    "commit: $(git rev-parse HEAD)"; "tracked files: $((git ls-files | Measure-Object).Count)"

    Step "fresh venv from lockfile"
    $env:ASD_PYTHON = 'C:\Users\Admin\miniconda3\python.exe'
    .\tasks.ps1 setup *>&1 | ForEach-Object { "$_" } | Select-String -Pattern '==>|Successfully installed' | ForEach-Object { $_.Line.Substring(0, [Math]::Min(160, $_.Line.Length)) }
    & .\.venv-embedding\Scripts\python.exe --version

    Step "local configuration written by the 'new user' (different password + port; values not logged)"
    $pw = -join ((48..57) + (97..122) | Get-Random -Count 24 | ForEach-Object { [char]$_ })
    Set-Content -Encoding ascii deployments\rag-db.env "RAG_DB_PASSWORD=$pw"
    (Get-Content deployments\database.env.example) -replace '^RAG_DATABASE_URL=.*$', "RAG_DATABASE_URL=postgresql://postgres:${pw}@127.0.0.1:5435/asd_rag" | Set-Content -Encoding ascii deployments\database.env
    "git ignores local config: " + ((git check-ignore deployments/rag-db.env deployments/database.env) -join ', ')

    Step "transfer backup (not in git): copy dump + .sha256"
    New-Item -ItemType Directory transfer | Out-Null
    Copy-Item "$Source\backups\$Dump", "$Source\backups\$Dump.sha256" transfer\

    Step "db-up on Docker WITHOUT the volume (must create volume + container)"
    .\tasks.ps1 db-up *>&1 | ForEach-Object { "$_" }

    Step "db-bootstrap from the transferred backup"
    .\tasks.ps1 db-bootstrap "transfer\$Dump" *>&1 | ForEach-Object { "$_" }

    Step "db-bootstrap again must REFUSE (never restore over existing data)"
    $refused = $false
    try { .\tasks.ps1 db-bootstrap "transfer\$Dump" *>&1 | ForEach-Object { "$_" } } catch { $refused = $true; "refused as expected: $($_.Exception.Message)" }
    if (-not $refused) { throw 'second bootstrap did not refuse' }

    Step "tasks.ps1 all on the new cluster (pins must accept the different local connection)"
    .\tasks.ps1 all *>&1 | ForEach-Object { "$_" } | Where-Object { $_ -match '==>|NOTE|pins:|"status": "ok"|TOTAL|RESULT|VERIFIED \{"status"|"status"|secret scan|ALL CHECKS' } | ForEach-Object { $_.Substring(0, [Math]::Min(170, $_.Length)) }

    Step "F4: an existing DB with the old fixed name must survive; two restore-checks run concurrently"
    docker exec $c createdb -U postgres asd_rag_restore_check
    New-Item -ItemType Directory -Force backups | Out-Null; Copy-Item transfer\* backups\
    $jobs = 1..2 | ForEach-Object {
        Start-Job -ArgumentList $Clone -ScriptBlock {
            param($dir) Set-Location $dir
            $env:ASD_DB_PROJECT = 'asdboot'; $env:ASD_DB_VOLUME = 'asdboot_rag_data'; $env:ASD_DB_PORT = '5435'
            .\tasks.ps1 db-restore-check *>&1 | ForEach-Object { "$_" } | Select-String 'RESTORE CHECK|createdb|failed' | ForEach-Object { $_.Line }
        }
    }
    $results = $jobs | Wait-Job | Receive-Job
    $results
    if (($results | Where-Object { $_ -match 'RESTORE CHECK PASS' }).Count -ne 2) { throw 'concurrent restore-checks did not both pass' }
    $jobs | Remove-Job
    "databases left in test cluster:"; docker exec $c psql -U postgres -Atc "select datname from pg_database where datname like 'asd%' order by 1"
    $kept = docker exec $c psql -U postgres -Atc "select count(*) from pg_database where datname='asd_rag_restore_check'"
    $leftovers = docker exec $c psql -U postgres -Atc "select count(*) from pg_database where datname like 'asd_restore_check_%'"
    if ("$kept".Trim() -ne '1') { throw 'pre-existing database was removed' }
    if ("$leftovers".Trim() -ne '0') { throw 'restore-check left temporary databases behind' }
    'pre-existing DB kept; no temporary DBs left'
}
finally {
    Step "teardown: only the isolated test container + the test volume created above"
    Set-Location $env:TEMP
    $ErrorActionPreference = 'Continue'
    if (Test-Path "$Clone\deployments\compose.rag.yml") {
        docker compose -p asdboot -f "$Clone\deployments\compose.rag.yml" --env-file "$Clone\deployments\rag-db.env" down 2>&1 | ForEach-Object { "$_" }
    }
    # Windows PowerShell 5.1 drops embedded double quotes in native arguments, so read labels as JSON.
    $label = (docker volume inspect asdboot_rag_data 2>$null | ConvertFrom-Json).Labels.asd_agent
    if ($label -eq 'rag-db') { docker volume rm asdboot_rag_data | ForEach-Object { "removed test volume $_" } }
    $liveAfter = (Live-Hashes) -join "`n"
    "original DB unchanged: $($liveAfter -eq $liveBefore)"
    "original container: $(docker inspect -f '{{.State.Health.Status}}' deployments-rag-db-1)"
}
