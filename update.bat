@echo off
chcp 65001 >nul
echo [1/3] Generating static HTML...
C:\Users\14507\.workbuddy\binaries\python\versions\3.13.12\python.exe "D:\taishiji_workbuddy\charging_dashboard\site\generate.py"
if errorlevel 1 (
    echo ERROR: Failed to generate HTML
    exit /b 1
)

echo [2/3] Pushing to GitHub...
cd /d "D:\taishiji_workbuddy\charging_dashboard\site"
git add index.html
git commit -m "Update: refresh charging data (%date% %time%)" 2>nul
git push origin main
if errorlevel 1 (
    echo WARNING: Push may have failed, but site may still be updated
)

echo [3/3] Done! Site will update at https://charging-dashboard.pages.dev
echo (Usually within 10-30 seconds)
pause
