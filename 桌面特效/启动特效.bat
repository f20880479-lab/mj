@echo off
cd /d "%~dp0"
for %%f in ("%~dp0*.pyw") do start "" pythonw "%%f"
