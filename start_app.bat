@echo off
:loop
echo [%date% %time%] Menjalankan Garindra Produksi...
py app.py
echo [%date% %time%] Program berhenti/crash, restart otomatis dalam 5 detik...
timeout /t 5
goto loop
