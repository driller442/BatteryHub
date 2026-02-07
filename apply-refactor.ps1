Write-Host "📄 Extracting patch..." -ForegroundColor Cyan
$pasteFile = "C:\Agent Zero shared\BatteryHub\paste.txt"
$patchFile = "C:\Users\aiaio\Downloads\batteryhub-phases2-4.patch"
if (-not (Test-Path $pasteFile)) { Write-Host "❌ paste.txt not found" -ForegroundColor Red; exit 1 }
$content = Get-Content -Path $pasteFile -Raw
$patchStart = $content.IndexOf("diff --git")
if ($patchStart -eq -1) { Write-Host "❌ No patch found" -ForegroundColor Red; exit 1 }
$patchContent = $content.Substring($patchStart)
$patchContent | Out-File -FilePath $patchFile -Encoding UTF8 -NoNewline
Write-Host "✅ Patch extracted" -ForegroundColor Green
Set-Location "C:\Agent Zero shared\BatteryHub"
Write-Host "🔧 Applying patch..." -ForegroundColor Cyan
git apply $patchFile 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { git apply --whitespace=fix $patchFile 2>&1 | Out-Null }
if (Test-Path ".\src") { Write-Host "✅ Patch applied!" -ForegroundColor Green } else { Write-Host "❌ Failed" -ForegroundColor Red; exit 1 }
Write-Host "📦 Installing deps..." -ForegroundColor Cyan
C:\Users\aiaio\AppData\Local\Programs\Python\Python311\python.exe -m pip install -q -r requirements.txt
git add .
git commit -m "Phase 2-4: Modular refactor" -q
Write-Host "🚀 Pushing to GitHub..." -ForegroundColor Cyan
git push origin main -q
if ($LASTEXITCODE -eq 0) { Write-Host "✅ SUCCESS!" -ForegroundColor Green } else { Write-Host "⚠️ Check manually" -ForegroundColor Yellow }
Write-Host "Done! Run: python monitor.py" -ForegroundColor Cyan
