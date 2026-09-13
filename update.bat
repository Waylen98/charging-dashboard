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

echo [2/3] Staging deployment files ...
if exist dist rmdir /s /q dist
mkdir dist
copy /y index.html dist\index.html >nul

echo [3/3] Deploying to Cloudflare Pages ...
npx --yes wrangler pages deploy dist --project-name=charging-dashboard --branch=main
if errorlevel 1 (
  echo [ERROR] deploy failed
  pause
  exit /b 1
)

echo.
echo Done: https://charging-dashboard.pages.dev
pause