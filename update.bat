@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo [1/3] Generating index.html from charging_records.json ...
python generate.py --json-input charging_records.json
if errorlevel 1 (
  echo [ERROR] generate failed
  pause
  exit /b 1
)

echo [2/3] Committing charging_records.json ...
git add charging_records.json
git diff --cached --quiet
if not errorlevel 1 (
  echo No changes to charging_records.json, nothing to push.
  pause
  exit /b 0
)
git commit -m "chore: 更新充电记录 (%date% %time%)"
if errorlevel 1 (
  echo [WARN] commit returned an error
)

echo [3/3] Pushing to GitHub ...
git push origin main
if errorlevel 1 (
  echo [ERROR] push failed - check network and git credentials
  pause
  exit /b 1
)

echo.
echo Pushed. Cloudflare builds and deploys automatically (1-2 min).
echo Live: https://charging-dashboard.pages.dev
pause