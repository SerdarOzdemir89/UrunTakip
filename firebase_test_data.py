#!/usr/bin/env python3
import firebase_admin
from firebase_admin import credentials, firestore
import os
from datetime import datetime

# Firebase Admin SDK başlatma
try:
    service_account_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'serviceAccountKey.json')
    if os.path.exists(service_account_path):
        cred = credentials.Certificate(service_account_path)
        firebase_admin.initialize_app(cred)
        print("Firebase Admin SDK başarıyla başlatıldı")
    else:
        firebase_admin.initialize_app()
        print("Firebase Admin SDK başarıyla başlatıldı (default)")
    
    db = firestore.client()
    print("Firestore client başarıyla oluşturuldu")
    
    # Test ürünü ekle
    products_ref = db.collection('products')
    
    # Çamaşır Makinesi test ürünü
    test_product = {
        'isletme': 'Çamaşır Makinesi İşletmesi',
        'model_no': 'WM-2024-001',
        'seri_no': 'CM123456789',
        'jira_no': 'JIRA-WM-001',
        'gorsel_path': None,
        'durum': 'Yolda',
        'teslim_alan': None,
        'teslim_alma_tarihi': None,
        'laboratuvarlar': 'EMC,Safety',
        'aciklama': 'Test ürünü - Çamaşır makinesi Firebase güncellemesi',
        'created_at': firestore.SERVER_TIMESTAMP,
        'updated_at': firestore.SERVER_TIMESTAMP
    }
    
    doc_ref = products_ref.add(test_product)
    product_id = doc_ref[1].id
    print(f"Test ürünü Firebase'e eklendi: {product_id}")
    
    # Laboratuvar durumları ekle
    lab_status_ref = db.collection('laboratory_status')
    
    # EMC laboratuvarı
    emc_status = {
        'product_id': product_id,
        'laboratuvar': 'EMC',
        'durum': 'Yolda',
        'hurda_tarihi': None,
        'hurda_aciklama': None,
        'created_at': firestore.SERVER_TIMESTAMP
    }
    lab_status_ref.add(emc_status)
    print("EMC laboratuvar durumu eklendi")
    
    # Safety laboratuvarı
    safety_status = {
        'product_id': product_id,
        'laboratuvar': 'Safety',
        'durum': 'Yolda',
        'hurda_tarihi': None,
        'hurda_aciklama': None,
        'created_at': firestore.SERVER_TIMESTAMP
    }
    lab_status_ref.add(safety_status)
    print("Safety laboratuvar durumu eklendi")
    
    print("✅ Firebase test verileri başarıyla eklendi!")
    print("🔄 Artık web arayüzünde Çamaşır Makinesi İşletmesi ve seri numarası görünecek")
    
except Exception as e:
    print(f"❌ Hata: {e}")
