@echo off
REM Bu betik, Depo_Takip uygulamasını başlatır.

REM Betiğin çalıştığı dizine git
cd /d "%~dp0"

echo Gerekli Python kütüphaneleri kontrol ediliyor ve yukleniyor...
pip install -r requirements.txt

echo Flask uygulamasi baslatiliyor...
python app.py

REM Uygulama kapandiginda pencerenin hemen kapanmamasi icin
pause 