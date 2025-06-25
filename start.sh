#!/bin/bash
# Bu betik, Depo_Takip uygulamasını başlatır.

# Betiğin çalıştığı dizine git
cd "$(dirname "$0")"

echo "Gerekli Python kütüphaneleri kontrol ediliyor ve yükleniyor..."
# Kütüphaneleri yükle (zaten yüklüyse hızlıca geçer)
pip install -r requirements.txt

echo "Flask uygulaması başlatılıyor..."
# Flask uygulamasını çalıştır
python app.py 