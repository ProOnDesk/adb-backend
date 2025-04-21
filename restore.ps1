$DB_CONTAINER = "adb-backend-db-1"
$BACKUP_FILE = "db_backups\backup.dump"

if (-not (Test-Path $BACKUP_FILE)) {
    Write-Host "❌ Backup file not found: $BACKUP_FILE"
    exit
}

Get-Content $BACKUP_FILE | docker exec -i $DB_CONTAINER pg_restore -U postgres -d postgres
Write-Host "✅ Restore completed from $BACKUP_FILE"