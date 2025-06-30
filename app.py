from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory, current_app, jsonify
import firebase_admin
from firebase_admin import credentials, firestore, auth as firebase_auth, storage as firebase_storage
from datetime import datetime
import os
import logging
import json
from functools import wraps
from werkzeug.utils import secure_filename
from urllib.parse import urljoin

# Logging ayarları
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'gizli-anahtar-123'
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static/images')
app.config['DEFAULT_LOGO_PATH'] = 'static/images/owl-logo.png'

# Firebase Admin SDK başlatma
try:
    service_account_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'serviceAccountKey.json')
    if os.path.exists(service_account_path):
        cred = credentials.Certificate(service_account_path)
        firebase_admin.initialize_app(cred)
        logger.debug("Firebase Admin SDK başarıyla başlatıldı")
    else:
        firebase_admin.initialize_app()
        logger.debug("Firebase Admin SDK başarıyla başlatıldı (default)")
    
    db = firestore.client()
    FIREBASE_ENABLED = True
    logger.debug("Firestore client başarıyla oluşturuldu")
    
except Exception as e:
    db = None
    FIREBASE_ENABLED = False
    logger.error(f"Firebase Admin SDK başlatılamadı: {e}")

# Debug bilgisi
logger.debug(f"Uygulama başlatıldı")
logger.debug(f"Çalışma dizini: {os.getcwd()}")
logger.debug(f"Upload dizini: {app.config['UPLOAD_FOLDER']}")
logger.debug(f"Varsayılan logo: {app.config['DEFAULT_LOGO_PATH']}")

# Eğer static/images klasörü yoksa oluştur
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])
    logger.debug(f"Upload dizini oluşturuldu: {app.config['UPLOAD_FOLDER']}")

# Sabit listeler
isletmeler = [
    'Pişirici Cihazlar İşletmesi',
    'Buzdolabı İşletmesi',
    'Temin Ürün Direktörlüğü',
    'Bulaşık Makinesi İşletmesi',
    'Kurutucu İşletmesi',
    'Küçük Ev Aletleri İşletmesi',
    'Beko Wuxi R&D',
    'Hitachi',
    'Dawlance'
]

laboratuvarlar = [
    'EMC',
    'İklimlendirme ve Titreşim',
    'Dokunmatik Performans',
    'Optik Performans',
    'Komponent',
    'Gerilim Performans',
    'Derating',
    'Safety',
    'Standby'
]

LABORATUVAR_DURUM_SECENEKLERI = [
    'Bekleme Alanında',
    'Laboratuvarda',
    'Transfer Edildi',
    'Hurda',
    'Bekleniyor',
    'Tamamlandı'
]

# Firebase Firestore Fonksiyonlar
def get_users_collection():
    if not FIREBASE_ENABLED or not db:
        return None
    return db.collection('users')

def get_products_collection():
    if not FIREBASE_ENABLED or not db:
        return None
    return db.collection('products')

def get_laboratory_status_collection():
    if not FIREBASE_ENABLED or not db:
        return None
    return db.collection('laboratory_status')

def get_logs_collection():
    if not FIREBASE_ENABLED or not db:
        return None
    return db.collection('logs')

def create_user(username, password, role, isletme=None):
    try:
        users_ref = get_users_collection()
        if not users_ref:
            return None
            
        user_data = {
            'username': username,
            'password': password,
            'role': role,
            'isletme': isletme,
            'created_at': firestore.SERVER_TIMESTAMP
        }
        
        doc_ref = users_ref.add(user_data)
        logger.debug(f"Kullanıcı oluşturuldu: {doc_ref[1].id}")
        return doc_ref[1].id
    except Exception as e:
        logger.error(f"Kullanıcı oluşturma hatası: {e}")
        return None

def get_user_by_username(username):
    try:
        users_ref = get_users_collection()
        if not users_ref:
            return None
            
        query = users_ref.where('username', '==', username).limit(1)
        results = query.stream()
        
        for doc in results:
            user_data = doc.to_dict()
            user_data['id'] = doc.id
            return user_data
        
        return None
    except Exception as e:
        logger.error(f"Kullanıcı arama hatası: {e}")
        return None

def create_product(data):
    try:
        products_ref = get_products_collection()
        if not products_ref:
            return None
            
        product_data = {
            'isletme': data.get('isletme'),
            'model_no': data.get('model_no'),
            'seri_no': data.get('seri_no'),
            'jira_no': data.get('jira_no'),
            'gorsel_path': data.get('gorsel_path'),
            'gonderim_tarihi': firestore.SERVER_TIMESTAMP,
            'durum': data.get('durum', 'Yolda'),
            'teslim_alan': data.get('teslim_alan'),
            'teslim_alma_tarihi': data.get('teslim_alma_tarihi'),
            'laboratuvarlar': data.get('laboratuvarlar'),
            'aciklama': data.get('aciklama'),
            'urun_tipi': data.get('urun_tipi'),
            'created_at': firestore.SERVER_TIMESTAMP
        }
        
        doc_ref = products_ref.add(product_data)
        logger.debug(f"Ürün oluşturuldu: {doc_ref[1].id}")
        return doc_ref[1].id
    except Exception as e:
        logger.error(f"Ürün oluşturma hatası: {e}")
        return None

def get_all_products():
    try:
        products_ref = get_products_collection()
        if not products_ref:
            return []
            
        query = products_ref.order_by('created_at', direction=firestore.Query.DESCENDING)
        results = query.stream()
        
        products = []
        for doc in results:
            product_data = doc.to_dict()
            product_data['id'] = doc.id
            
            # Laboratuvar durumlarını getir
            lab_status = get_laboratory_status_for_product(doc.id)
            product_data['laboratuvar_durumlari'] = lab_status
            
            products.append(product_data)
        
        return products
    except Exception as e:
        logger.error(f"Ürün listesi alma hatası: {e}")
        return []

def get_product_by_id(product_id):
    try:
        products_ref = get_products_collection()
        if not products_ref:
            return None
            
        doc_ref = products_ref.document(product_id)
        doc = doc_ref.get()
        
        if doc.exists:
            product_data = doc.to_dict()
            product_data['id'] = doc.id
            
            # Firebase Timestamp'lerini datetime'a çevir
            if 'created_at' in product_data and product_data['created_at']:
                try:
                    product_data['gonderim_tarihi'] = product_data['created_at'].replace(tzinfo=None)
                except:
                    product_data['gonderim_tarihi'] = None
            
            if 'teslim_alma_tarihi' in product_data and product_data['teslim_alma_tarihi']:
                try:
                    if isinstance(product_data['teslim_alma_tarihi'], str):
                        from datetime import datetime
                        product_data['teslim_alma_tarihi'] = datetime.strptime(product_data['teslim_alma_tarihi'], '%Y-%m-%d')
                except:
                    pass
            
            # Laboratuvar durumlarını getir
            lab_status = get_laboratory_status_for_product(doc.id)
            product_data['laboratuvar_durumlari'] = lab_status
            
            return product_data
        
        return None
    except Exception as e:
        logger.error(f"Ürün getirme hatası: {e}")
        return None

def create_laboratory_status(product_id, laboratuvar, durum=None):
    try:
        lab_status_ref = get_laboratory_status_collection()
        if not lab_status_ref:
            return None
            
        status_data = {
            'product_id': product_id,
            'laboratuvar': laboratuvar,
            'durum': durum,
            'hurda_tarihi': None,
            'hurda_aciklama': None,
            'created_at': firestore.SERVER_TIMESTAMP
        }
        
        doc_ref = lab_status_ref.add(status_data)
        logger.debug(f"Laboratuvar durumu oluşturuldu: {doc_ref[1].id}")
        return doc_ref[1].id
    except Exception as e:
        logger.error(f"Laboratuvar durumu oluşturma hatası: {e}")
        return None

def get_laboratory_status_for_product(product_id):
    try:
        lab_status_ref = get_laboratory_status_collection()
        if not lab_status_ref:
            return []
            
        query = lab_status_ref.where('product_id', '==', product_id)
        results = query.stream()
        
        statuses = []
        for doc in results:
            status_data = doc.to_dict()
            status_data['id'] = doc.id
            statuses.append(status_data)
        
        return statuses
    except Exception as e:
        logger.error(f"Laboratuvar durumu getirme hatası: {e}")
        return []

def create_log_entry(user_id, username, action, product_id=None, details=None):
    try:
        logs_ref = get_logs_collection()
        if not logs_ref:
            return None
            
        log_data = {
            'user_id': user_id,
            'username': username,
            'action': action,
            'product_id': product_id,
            'details': details,
            'timestamp': firestore.SERVER_TIMESTAMP
        }
        
        doc_ref = logs_ref.add(log_data)
        logger.debug(f"Log kaydı oluşturuldu: {doc_ref[1].id}")
        return doc_ref[1].id
    except Exception as e:
        logger.error(f"Log kaydı oluşturma hatası: {e}")
        return None

def create_default_users():
    try:
        # Sadece tek admin hesabı oluştur
        admin_user = get_user_by_username('admin')
        if not admin_user:
            create_user('admin', 'admin123', 'admin')
            logger.debug("Admin kullanıcısı oluşturuldu")
            
        # Test kullanıcıları artık sadece 'user' rolü ile oluşturulacak
        test_users = [
            ('ebi', 'ebi123', 'user', 'Eskişehir Buzdolabı İşletmesi'),
            ('pci', 'pci123', 'user', 'Bolu Pişirici Cihazlar İşletmesi'),
            ('itt', 'itt123', 'user', None),
            ('gpt', 'gpt123', 'user', None),
            ('emc', 'emc123', 'user', None),
            ('derating', 'derating123', 'user', None),
            ('safety', 'safety123', 'user', None),
            ('dokunmatik', 'dokunmatik123', 'user', None)
        ]
        
        for username, password, role, isletme in test_users:
            existing_user = get_user_by_username(username)
            if not existing_user:
                create_user(username, password, role, isletme)
                logger.debug(f"{username} kullanıcısı oluşturuldu")
                
    except Exception as e:
        logger.error(f"Varsayılan kullanıcı oluşturma hatası: {e}")

# Decorators
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Lütfen önce giriş yapın.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'admin':
            flash('Bu sayfaya erişim yetkiniz yok.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = get_user_by_username(username)
        
        if user and user['password'] == password:
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            session['isletme'] = user.get('isletme')
            
            create_log_entry(user['id'], user['username'], 'Giriş Yaptı')
            flash('Başarıyla giriş yaptınız!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Kullanıcı adı veya şifre hatalı!', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    if 'user_id' in session:
        create_log_entry(session['user_id'], session['username'], 'Çıkış Yaptı')
    
    session.clear()
    flash('Başarıyla çıkış yaptınız.', 'success')
    return redirect(url_for('login'))

@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    try:
        isletme_filter = request.args.get('isletme', '')
        model_no_filter = request.args.get('model_no', '')
        jira_no_filter = request.args.get('jira_no', '')
        lab_filter = request.args.get('lab', '')
        durum_filter = request.args.get('durum', '')

        tum_urunler = get_all_products()
        
        urunler = []
        for urun in tum_urunler:
            # Durum filtresi kontrolü - eğer durum filtresi varsa ona göre göster
            if durum_filter:
                if urun.get('durum') != durum_filter:
                    continue
            else:
                # Durum filtresi yoksa hurda ürünleri gizle
                if urun.get('durum') == 'Hurda':
                    continue
                
            if isletme_filter and urun.get('isletme', '') != isletme_filter:
                continue
                
            if model_no_filter and model_no_filter.lower() not in urun.get('model_no', '').lower():
                continue
                
            if jira_no_filter and jira_no_filter.lower() not in urun.get('jira_no', '').lower():
                continue
                
            if lab_filter:
                lab_found = False
                for lab_durum in urun.get('laboratuvar_durumlari', []):
                    if lab_durum.get('laboratuvar') == lab_filter:
                        lab_found = True
                        break
                if not lab_found:
                    continue
                
            urunler.append(urun)

        logger.info(f"Ana ekranda listelenecek ürün sayısı: {len(urunler)}")
        
        return render_template('index.html', 
                             urunler=urunler, 
                             isletmeler=isletmeler,
                             laboratuvarlar=laboratuvarlar)
                             
    except Exception as e:
        logger.error(f'Ana sayfa yükleme hatası: {str(e)}')
        flash('Ana sayfa yüklenirken bir hata oluştu!', 'error')
        return render_template('index.html', urunler=[], isletmeler=isletmeler, laboratuvarlar=laboratuvarlar)

@app.route('/urun_ekle', methods=['POST'])
@login_required
def urun_ekle():
    try:
        logger.debug("[DEBUG] Ürün ekleme fonksiyonu BAŞLADI")
        
        logger.debug(f"[DEBUG] Kullanıcı admin mi? {session.get('role') == 'admin'}")

        isletme = request.form.get('isletme')
        model_no = request.form.get('model_no')
        seri_no = request.form.get('seri_no')
        jira_no = request.form.get('jira_no')
        aciklama = request.form.get('aciklama', '')
        laboratuvarlar_list = request.form.getlist('laboratuvarlar')

        logger.debug(f"[DEBUG] Formdan gelenler: isletme={isletme}, model_no={model_no}, seri_no={seri_no}, jira_no={jira_no}, laboratuvarlar={laboratuvarlar_list}")

        gorsel_path = None
        if 'gorsel' in request.files:
            file = request.files['gorsel']
            if file and file.filename != '':
                filename = secure_filename(file.filename)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
                filename = timestamp + filename
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                gorsel_path = f'static/images/{filename}'

        logger.debug(f"[DEBUG] Kullanılacak görsel: {gorsel_path}")

        product_data = {
            'isletme': isletme,
            'model_no': model_no,
            'seri_no': seri_no,
            'jira_no': jira_no,
            'gorsel_path': gorsel_path,
            'durum': 'Yolda',
            'laboratuvarlar': ','.join(laboratuvarlar_list) if laboratuvarlar_list else '',
            'aciklama': aciklama
        }

        logger.debug("[DEBUG] Yeni ürün nesnesi oluşturuldu")

        product_id = create_product(product_data)
        
        if not product_id:
            flash('Ürün eklenirken bir hata oluştu!', 'error')
            return redirect(url_for('index'))

        logger.debug("[DEBUG] Yeni ürün Firebase'e kaydedildi")

        for lab in laboratuvarlar_list:
            create_laboratory_status(product_id, lab, 'Yolda')

        logger.debug("[DEBUG] Laboratuvar durumları Firebase'e kaydedildi")

        create_log_entry(
            session['user_id'],
            session['username'],
            f'Yeni Ürün Eklendi: {model_no}',
            product_id,
            json.dumps({
                'model_no': model_no,
                'seri_no': seri_no,
                'jira_no': jira_no,
                'isletme': isletme
            })
        )

        logger.debug("[DEBUG] Log kaydı oluşturuldu ve Firebase'e kaydedildi")

        logger.info(f"Ürün başarıyla eklendi. Ürün ID: {product_id}, Seri No: {seri_no}, Ekleyen Kullanıcı: {session['username']}")
        flash('Ürün başarıyla eklendi!', 'success')
        return redirect(url_for('index'))

    except Exception as e:
        logger.error(f'Ürün ekleme hatası: {str(e)}')
        flash('Ürün eklenirken bir hata oluştu!', 'error')
        return redirect(url_for('index'))

@app.route('/firebase-test')
@login_required
def firebase_test():
    return render_template('firebase_test.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        # Yeni kayıtlar otomatik olarak 'user' rolü alır
        role = 'user'
        isletme = request.form.get('isletme', None)

        if get_user_by_username(username):
            flash('Bu kullanıcı adı zaten alınmış!', 'danger')
            return render_template('register.html')

        user_id = create_user(username, password, role, isletme)
        
        if user_id:
            flash('Kayıt başarılı! Giriş yapabilirsiniz.', 'success')
            return redirect(url_for('login'))
        else:
            flash('Kayıt sırasında bir hata oluştu!', 'danger')
            
    return render_template('register.html')

@app.route('/urun_detay/<product_id>')
@login_required
def urun_detay(product_id):
    try:
        urun = get_product_by_id(product_id)
        if not urun:
            flash('Ürün bulunamadı!', 'error')
            return redirect(url_for('index'))
        
        # Ürün geçmişini getir
        urun_log_kayitlari = []
        try:
            logs_ref = get_logs_collection()
            if logs_ref:
                query = logs_ref.where('product_id', '==', product_id).order_by('timestamp', direction=firestore.Query.DESCENDING)
                results = query.stream()
                
                for doc in results:
                    log_data = doc.to_dict()
                    log_data['id'] = doc.id
                    
                    # Timestamp'i datetime'a çevir
                    if 'timestamp' in log_data and log_data['timestamp']:
                        try:
                            if hasattr(log_data['timestamp'], 'seconds'):
                                log_data['timestamp'] = datetime.fromtimestamp(log_data['timestamp'].seconds)
                            elif isinstance(log_data['timestamp'], str):
                                log_data['timestamp'] = datetime.fromisoformat(log_data['timestamp'].replace('Z', '+00:00'))
                        except:
                            log_data['timestamp'] = datetime.now()
                    else:
                        log_data['timestamp'] = datetime.now()
                    
                    urun_log_kayitlari.append(log_data)
        except Exception as e:
            logger.error(f'Ürün log kayıtları getirme hatası: {str(e)}')
        
        return render_template('urun_detay.html', urun=urun, urun_log_kayitlari=urun_log_kayitlari)
    except Exception as e:
        logger.error(f'Ürün detay hatası: {str(e)}')
        flash('Ürün detayları yüklenirken bir hata oluştu!', 'error')
        return redirect(url_for('index'))

@app.route('/urun_duzenle/<product_id>', methods=['GET', 'POST'])
@login_required
def urun_duzenle(product_id):
    try:
        if request.method == 'POST':
            # Ürün güncelleme işlemi
            products_ref = get_products_collection()
            if products_ref:
                doc_ref = products_ref.document(product_id)
                
                update_data = {
                    'isletme': request.form.get('isletme'),
                    'model_no': request.form.get('model_no'),
                    'seri_no': request.form.get('seri_no'),
                    'jira_no': request.form.get('jira_no'),
                    'durum': request.form.get('durum'),
                    'teslim_alan': request.form.get('teslim_alan'),
                    'aciklama': request.form.get('aciklama', ''),
                    'updated_at': firestore.SERVER_TIMESTAMP
                }
                
                # Teslim alma tarihi
                teslim_tarihi = request.form.get('teslim_alma_tarihi')
                if teslim_tarihi:
                    update_data['teslim_alma_tarihi'] = teslim_tarihi
                
                doc_ref.update(update_data)
                
                # Log kaydı
                create_log_entry(
                    session['user_id'],
                    session['username'],
                    f'Ürün Güncellendi',
                    product_id,
                    json.dumps(update_data, default=str)
                )
                
                flash('Ürün başarıyla güncellendi!', 'success')
            
            return redirect(url_for('urun_detay', product_id=product_id))
        
        # GET request - form göster
        urun = get_product_by_id(product_id)
        if not urun:
            flash('Ürün bulunamadı!', 'error')
            return redirect(url_for('index'))
        
        return render_template('urun_duzenle.html', 
                             urun=urun, 
                             isletmeler=isletmeler,
                             LABORATUVAR_DURUM_SECENEKLERI=LABORATUVAR_DURUM_SECENEKLERI)
                             
    except Exception as e:
        logger.error(f'Ürün düzenleme hatası: {str(e)}')
        flash('Ürün düzenlenirken bir hata oluştu!', 'error')
        return redirect(url_for('index'))

@app.route('/gecmis')
@admin_required
def gecmis():
    try:
        # Firebase'den log kayıtlarını getir
        logs_ref = get_logs_collection()
        if logs_ref:
            query = logs_ref.order_by('timestamp', direction=firestore.Query.DESCENDING).limit(100)
            results = query.stream()
            
            loglar = []
            for doc in results:
                log_data = doc.to_dict()
                log_data['id'] = doc.id
                loglar.append(log_data)
        else:
            loglar = []
        
        return render_template('gecmis.html', loglar=loglar)
    except Exception as e:
        logger.error(f'Geçmiş sayfası hatası: {str(e)}')
        flash('Geçmiş kayıtları yüklenirken bir hata oluştu!', 'error')
        return render_template('gecmis.html', loglar=[])

@app.route('/rapor')
@admin_required
def rapor():
    try:
        # Firebase'den ürün istatistiklerini hesapla
        tum_urunler = get_all_products()
        
        # İstatistikleri hesapla
        toplam_urun = len(tum_urunler)
        
        durum_sayilari = {}
        isletme_sayilari = {}
        lab_sayilari = {}
        
        for urun in tum_urunler:
            # Durum istatistikleri
            durum = urun.get('durum', 'Belirtilmemiş')
            durum_sayilari[durum] = durum_sayilari.get(durum, 0) + 1
            
            # İşletme istatistikleri
            isletme = urun.get('isletme', 'Belirtilmemiş')
            isletme_sayilari[isletme] = isletme_sayilari.get(isletme, 0) + 1
            
            # Laboratuvar istatistikleri
            for lab_durum in urun.get('laboratuvar_durumlari', []):
                lab = lab_durum.get('laboratuvar', 'Belirtilmemiş')
                lab_sayilari[lab] = lab_sayilari.get(lab, 0) + 1
        
        return render_template('rapor.html',
                             toplam_urun=toplam_urun,
                             durum_sayilari=durum_sayilari,
                             isletme_sayilari=isletme_sayilari,
                             lab_sayilari=lab_sayilari)
                             
    except Exception as e:
        logger.error(f'Rapor sayfası hatası: {str(e)}')
        flash('Rapor yüklenirken bir hata oluştu!', 'error')
        return render_template('rapor.html',
                             toplam_urun=0,
                             durum_sayilari={},
                             isletme_sayilari={},
                             lab_sayilari={})

@app.route('/yillik_rapor')
@admin_required
def yillik_rapor():
    try:
        # Firebase'den aylık ürün sayılarını hesapla
        tum_urunler = get_all_products()
        
        # Aylık istatistikleri hesapla
        aylik_veriler = {}
        yillik_toplam = {}
        
        for urun in tum_urunler:
            # created_at timestamp'i kontrol et
            created_at = urun.get('created_at')
            if created_at:
                try:
                    # Firestore timestamp'i datetime'a çevir
                    if hasattr(created_at, 'seconds'):
                        tarih = datetime.fromtimestamp(created_at.seconds)
                    else:
                        tarih = created_at
                    
                    yil = tarih.year
                    ay = tarih.month
                    
                    if yil not in aylik_veriler:
                        aylik_veriler[yil] = {}
                        yillik_toplam[yil] = 0
                    
                    if ay not in aylik_veriler[yil]:
                        aylik_veriler[yil][ay] = 0
                    
                    aylik_veriler[yil][ay] += 1
                    yillik_toplam[yil] += 1
                    
                except Exception as e:
                    logger.error(f"Tarih çevirme hatası: {e}")
                    continue
        
        return render_template('yillik_rapor.html',
                             aylik_veriler=aylik_veriler,
                             yillik_toplam=yillik_toplam)
                             
    except Exception as e:
        logger.error(f'Yıllık rapor hatası: {str(e)}')
        flash('Yıllık rapor yüklenirken bir hata oluştu!', 'error')
        return render_template('yillik_rapor.html',
                             aylik_veriler={},
                             yillik_toplam={})

def update_product_status_based_on_labs(product_id):
    """Laboratuvar durumlarına göre ana ürün durumunu güncelle"""
    try:
        logger.debug(f"[DEBUG] update_product_status_based_on_labs başladı: product_id={product_id}")
        
        # Ürünün laboratuvar durumlarını getir
        lab_statuses = get_laboratory_status_for_product(product_id)
        
        if not lab_statuses:
            logger.debug(f"[DEBUG] Laboratuvar durumu bulunamadı: product_id={product_id}")
            return
        
        logger.debug(f"[DEBUG] Bulunan lab durumları: {[{'lab': ls.get('laboratuvar'), 'durum': ls.get('durum')} for ls in lab_statuses]}")
        
        # Durum öncelik sırası: Hurda > Transfer Edildi > Laboratuvarda > Bekleme Alanında > Yolda
        durum_oncelik = {
            'Hurda': 5,
            'Transfer Edildi': 4,
            'Laboratuvarda': 3,
            'Bekleme Alanında': 2,
            'Bekleme Alanı': 2,  # Aynı öncelik
            'Yolda': 1,
            'Ürün Bekleniyor': 0
        }
        
        # En yüksek öncelikli durumu bul
        en_yuksek_durum = None
        en_yuksek_oncelik = -1
        
        for lab_status in lab_statuses:
            durum = lab_status.get('durum', 'Yolda')
            oncelik = durum_oncelik.get(durum, 0)
            
            logger.debug(f"[DEBUG] Lab: {lab_status.get('laboratuvar')}, Durum: {durum}, Öncelik: {oncelik}")
            
            if oncelik > en_yuksek_oncelik:
                en_yuksek_oncelik = oncelik
                en_yuksek_durum = durum
        
        logger.debug(f"[DEBUG] En yüksek öncelikli durum: {en_yuksek_durum} (öncelik: {en_yuksek_oncelik})")
        
        # Ana ürün durumunu güncelle
        if en_yuksek_durum:
            products_ref = get_products_collection()
            if products_ref:
                doc_ref = products_ref.document(product_id)
                doc_ref.update({
                    'durum': en_yuksek_durum,
                    'updated_at': firestore.SERVER_TIMESTAMP
                })
                logger.debug(f"[DEBUG] Ana ürün durumu güncellendi: {en_yuksek_durum}")
            else:
                logger.error("[ERROR] Products collection bulunamadı")
        else:
            logger.debug("[DEBUG] Güncellenecek durum bulunamadı")
        
    except Exception as e:
        logger.error(f'Ürün durum güncelleme hatası: {str(e)}')

@app.route('/laboratuvar_durum_guncelle/<status_id>', methods=['POST'])
@login_required
def laboratuvar_durum_guncelle(status_id):
    try:
        yeni_durum = request.form.get('yeni_durum')
        hurda_aciklama = request.form.get('hurda_aciklama', '')
        
        logger.debug(f"[DEBUG] Laboratuvar durum güncelleme: status_id={status_id}, yeni_durum={yeni_durum}")
        
        # Firebase'de laboratuvar durumunu güncelle
        lab_status_ref = get_laboratory_status_collection()
        product_id = None
        
        if lab_status_ref:
            doc_ref = lab_status_ref.document(status_id)
            
            # Önce mevcut durumu al (product_id için)
            current_status = doc_ref.get()
            if current_status.exists:
                current_data = current_status.to_dict()
                product_id = current_data.get('product_id')
                logger.debug(f"[DEBUG] Mevcut durum: {current_data.get('durum')} -> Yeni durum: {yeni_durum}")
                logger.debug(f"[DEBUG] Product ID: {product_id}")
            else:
                logger.error(f"[ERROR] Laboratuvar durumu bulunamadı: {status_id}")
                flash('Laboratuvar durumu bulunamadı!', 'error')
                return redirect(request.referrer or url_for('index'))
            
            update_data = {
                'durum': yeni_durum,
                'updated_at': firestore.SERVER_TIMESTAMP
            }
            
            if yeni_durum == 'Hurda':
                update_data['hurda_tarihi'] = firestore.SERVER_TIMESTAMP
                update_data['hurda_aciklama'] = hurda_aciklama
            
            doc_ref.update(update_data)
            logger.debug(f"[DEBUG] Laboratuvar durumu güncellendi: {update_data}")
            
            # Ana ürün durumunu laboratuvar durumlarına göre güncelle
            if product_id:
                logger.debug(f"[DEBUG] Ana ürün durumu güncelleniyor...")
                update_product_status_based_on_labs(product_id)
            
            # Log kaydı
            create_log_entry(
                session['user_id'],
                session['username'],
                f'Laboratuvar Durumu Güncellendi: {yeni_durum}',
                product_id,
                json.dumps({'status_id': status_id, 'yeni_durum': yeni_durum})
            )
            
            flash('Laboratuvar durumu güncellendi!', 'success')
        else:
            logger.error("[ERROR] Laboratory status collection bulunamadı")
            flash('Veritabanı bağlantı hatası!', 'error')
        
        return redirect(request.referrer or url_for('index'))
        
    except Exception as e:
        logger.error(f'Laboratuvar durum güncelleme hatası: {str(e)}')
        flash('Laboratuvar durumu güncellenirken bir hata oluştu!', 'error')
        return redirect(request.referrer or url_for('index'))

@app.route('/bekleme_alani_yap/<urun_id>', methods=['POST'])
@admin_required
def bekleme_alani_yap(urun_id):
    try:
        # Ürünü bekleme alanına gönder
        products_ref = get_products_collection()
        if products_ref:
            doc_ref = products_ref.document(urun_id)
            doc_ref.update({
                'durum': 'Bekleme Alanında',
                'updated_at': firestore.SERVER_TIMESTAMP
            })
            
            # Tüm laboratuvar durumlarını da bekleme alanına güncelle
            lab_status_ref = get_laboratory_status_collection()
            if lab_status_ref:
                query = lab_status_ref.where('product_id', '==', urun_id)
                lab_statuses = query.stream()
                
                for lab_status in lab_statuses:
                    lab_status.reference.update({
                        'durum': 'Bekleme Alanında',
                        'updated_at': firestore.SERVER_TIMESTAMP
                    })
            
            # Log kaydı
            create_log_entry(
                session['user_id'],
                session['username'],
                'Ürün Bekleme Alanına Gönderildi',
                urun_id,
                f'Ürün ve tüm laboratuvarları bekleme alanına gönderildi'
            )
            
            flash('Ürün bekleme alanına gönderildi!', 'success')
        
        return redirect(url_for('index'))
        
    except Exception as e:
        logger.error(f'Bekleme alanına gönderme hatası: {str(e)}')
        flash('Ürün bekleme alanına gönderilirken bir hata oluştu!', 'error')
        return redirect(url_for('index'))

@app.route('/hurda_et/<urun_id>', methods=['POST'])
@admin_required
def hurda_et(urun_id):
    try:
        hurda_aciklama = request.form.get('hurda_aciklama', '')
        
        logger.debug(f"[DEBUG] Hurda etme işlemi başladı: urun_id={urun_id}, aciklama={hurda_aciklama}")
        
        # Ürünü hurda et
        products_ref = get_products_collection()
        if products_ref:
            doc_ref = products_ref.document(urun_id)
            doc_ref.update({
                'durum': 'Hurda',
                'hurda_tarihi': firestore.SERVER_TIMESTAMP,
                'hurda_aciklama': hurda_aciklama,
                'updated_at': firestore.SERVER_TIMESTAMP
            })
            logger.debug(f"[DEBUG] Ana ürün hurda edildi: {urun_id}")
            
            # Tüm laboratuvar durumlarını da hurda yap
            lab_status_ref = get_laboratory_status_collection()
            if lab_status_ref:
                query = lab_status_ref.where('product_id', '==', urun_id)
                lab_statuses = query.stream()
                
                hurda_lab_count = 0
                for lab_status in lab_statuses:
                    lab_status.reference.update({
                        'durum': 'Hurda',
                        'hurda_tarihi': firestore.SERVER_TIMESTAMP,
                        'hurda_aciklama': hurda_aciklama,
                        'updated_at': firestore.SERVER_TIMESTAMP
                    })
                    hurda_lab_count += 1
                
                logger.debug(f"[DEBUG] {hurda_lab_count} laboratuvar durumu hurda edildi")
            
            # Log kaydı
            create_log_entry(
                session['user_id'],
                session['username'],
                'Ürün Hurda Edildi',
                urun_id,
                f'Hurda açıklama: {hurda_aciklama} - Tüm laboratuvarlar hurda edildi'
            )
            
            flash('Ürün hurda edildi!', 'success')
        else:
            logger.error("[ERROR] Products collection bulunamadı")
            flash('Veritabanı bağlantı hatası!', 'error')
        
        return redirect(url_for('index'))
        
    except Exception as e:
        logger.error(f'Hurda etme hatası: {str(e)}')
        flash('Ürün hurda edilirken bir hata oluştu!', 'error')
        return redirect(url_for('index'))

if __name__ == '__main__':
    if FIREBASE_ENABLED:
        create_default_users()
    
    import os
    port = int(os.environ.get('PORT', 5003))
    debug = os.environ.get('FLASK_DEBUG', 'True').lower() == 'true'
    
    app.run(debug=debug, host='0.0.0.0', port=port)
