$DB_CONTAINER = "adb-backend-db-1"
$BACKUP_DIR = "db_backups"
$FILE = "$BACKUP_DIR\backup.dump"

if (-not (Test-Path $BACKUP_DIR)) {
    New-Item -ItemType Directory -Path $BACKUP_DIR | Out-Null
}

docker exec -t $DB_CONTAINER pg_dump -U postgres -F c -d postgres > $FILE
Write-Host "✅ Backup saved to $FILE"
