$files = @(
  "src\dex\nado_api.py",
  "src\tg\notification_bot.py",
  "src\utils\database.py",
  "src\utils\report_generator.py",
  "src\ml\trend_predictor.py",
  "src\ml\data_manager.py"
)
foreach ($f in $files) {
  $full = Join-Path "C:\Project\Trading_bot" $f
  Write-Host ""
  Write-Host "--- $f ---"
  Select-String -Pattern "def |class " -Path $full | ForEach-Object { $_.Line.Trim() }
}
