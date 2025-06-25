from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory, current_app, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os
import logging
import json
from functools import wraps
from werkzeug.utils import secure_filename
from flask_login import UserMixin, login_user, login_required, logout_user
import shutil
from urllib.parse import urljoin
from sqlalchemy.sql import extract
from sqlalchemy import func

# Logging ayarları
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'gizli-anahtar-123'  # Flash mesajları için gerekli
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(os.path.dirname(os.path.abspath(__file__)), 'depo_takip.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static/images')
app.config['DEFAULT_LOGO_PATH'] = 'static/images/owl-logo.png'

# Debug bilgisi
logger.debug(f"Uygulama başlatıldı")
logger.debug(f"Çalışma dizini: {os.getcwd()}")
logger.debug(f"Upload dizini: {app.config['UPLOAD_FOLDER']}")
logger.debug(f"Varsayılan logo: {app.config['DEFAULT_LOGO_PATH']}")

# Eğer static/images klasörü yoksa oluştur
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])
    logger.debug(f"Upload dizini oluşturuldu: {app.config['UPLOAD_FOLDER']}")

# Uploads klasörünü oluştur
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# Default logo klasörünü oluştur ve logoyu kopyala
default_logo_dir = os.path.dirname(os.path.join(app.root_path, app.config['DEFAULT_LOGO_PATH']))
if not os.path.exists(default_logo_dir):
    os.makedirs(default_logo_dir)
    logger.debug(f"Default logo dizini oluşturuldu: {default_logo_dir}")

# Varsayılan logoyu kontrol et
if not os.path.exists(app.config['DEFAULT_LOGO_PATH']):
    app.config['DEFAULT_LOGO_PATH'] = None

db = SQLAlchemy(app)

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

# Yeni laboratuvar durum seçenekleri
LABORATUVAR_DURUM_SECENEKLERI = [
    'Bekleme Alanında',
    'Laboratuvarda',
    'Transfer Edildi',
    'Hurda',
    'Bekleniyor',
    'Tamamlandı'
]

# Kullanıcı modeli
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'admin' veya 'isletme'
    isletme = db.Column(db.String(20), nullable=True)  # Sadece isletme kullanıcıları için

# Ürün-Laboratuvar ilişki tablosu
class UrunLaboratuvar(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    urun_id = db.Column(db.Integer, db.ForeignKey('urun.id'), nullable=False)
    laboratuvar = db.Column(db.String(100), nullable=False)
    durum = db.Column(db.String(50), default=None)  # Yolda, Laboratuvarda, Hurda -> Bekleme Alanında, Laboratuvarda, Transfer Edildi, Hurda
    hurda_tarihi = db.Column(db.DateTime, nullable=True)
    hurda_aciklama = db.Column(db.Text, nullable=True)

class Urun(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    isletme = db.Column(db.String(100), nullable=False)
    model_no = db.Column(db.String(50), nullable=False)
    seri_no = db.Column(db.String(50), nullable=False)
    jira_no = db.Column(db.String(50), nullable=False)
    gorsel_path = db.Column(db.String(200))
    gonderim_tarihi = db.Column(db.DateTime, default=datetime.utcnow)
    durum = db.Column(db.String(50), default=None)  # Yolda, Bekleme Alanında, Laboratuvarda, Hurda -> None
    teslim_alan = db.Column(db.String(100), nullable=True)
    teslim_alma_tarihi = db.Column(db.DateTime, nullable=True)
    laboratuvarlar = db.Column(db.String(200))
    aciklama = db.Column(db.Text, nullable=True)  # Yeni eklenen açıklama alanı
    urun_tipi = db.Column(db.String(20), nullable=True)  # Benchmark veya Test Ürünü
    laboratuvar_durumlari = db.relationship('UrunLaboratuvar', backref='urun', lazy=True)

    def get_laboratuvarlar(self):
        """Ürünün laboratuvarlarını liste olarak döndürür"""
        if not self.laboratuvarlar:
            return []
        return [lab.strip() for lab in self.laboratuvarlar.split(',') if lab.strip()]

    def get_aktif_laboratuvarlar(self):
        """Hurda olmayan laboratuvarları döndürür"""
        return [lab.laboratuvar for lab in self.laboratuvar_durumlari if lab.durum != 'Hurda']

# Log modeli
class LogEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    username = db.Column(db.String(80), nullable=False)
    action = db.Column(db.String(100), nullable=False)
    urun_id = db.Column(db.Integer, db.ForeignKey('urun.id'), nullable=True)
    details = db.Column(db.Text, nullable=True) # JSON string olarak saklanacak
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<LogEntry {self.action} by {self.username} at {self.timestamp}>'

# Login gerektiren sayfalar için decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Lütfen önce giriş yapın.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Admin gerektiren sayfalar için decorator
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
        user = User.query.filter_by(username=username).first()
        
        if user and user.password == password:  # Gerçek uygulamada şifre hash'lenmelidir!
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
            session['isletme'] = user.isletme
            flash('Başarıyla giriş yaptınız!', 'success')
            return redirect(url_for('index'))
        
        flash('Kullanıcı adı veya şifre hatalı!', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Başarıyla çıkış yaptınız.', 'success')
    return redirect(url_for('login'))

@app.route('/')
def index():
    try:
        urunler = Urun.query.order_by(Urun.gonderim_tarihi.desc()).all()
        # Filtre parametrelerini tekrar ekle
        isletme = request.args.get('isletme', '')
        model_no = request.args.get('model_no', '')
        jira_no = request.args.get('jira_no', '')
        lab = request.args.get('lab', '')
        durum = request.args.get('durum', '')

        # Eğer hiçbir filtre yoksa (yani ana sayfa açılışı), sadece laboratuvarda olan ürünleri göster
        filtre_var_mi = any([isletme, model_no, jira_no, lab, durum])
        if not filtre_var_mi or (durum == ''):
            urunler = Urun.query.order_by(Urun.gonderim_tarihi.desc()).all()
        else:
            # Öncelik: Hurda
            if durum == 'Hurda':
                urunler = [u for u in urunler if u.durum == 'Hurda']
            else:
                if isletme:
                    urunler = [u for u in urunler if (u.isletme and u.isletme.strip().lower() == isletme.strip().lower())]
                if model_no:
                    urunler = [u for u in urunler if model_no.lower() in (u.model_no or '').lower()]
                if jira_no:
                    urunler = [u for u in urunler if jira_no.lower() in (u.jira_no or '').lower()]
                if lab:
                    urunler = [u for u in urunler if lab in (u.laboratuvarlar or '')]
                if durum:
                    urunler = [u for u in urunler if u.durum == durum]
        app.logger.info(f'Ana ekranda listelenecek ürün sayısı: {len(urunler)}')
        for u in urunler[:5]:
            app.logger.info(f'Ürün: model_no={u.model_no}, durum={u.durum}, isletme={u.isletme}')
        laboratuvarlar_filtre = list(set(laboratuvarlar + LABORATUVAR_DURUM_SECENEKLERI))
        laboratuvarlar_filtre.sort()
        return render_template('index.html', 
                             urunler=urunler,
                             laboratuvarlar=laboratuvarlar_filtre,
                             isletmeler=isletmeler)
    except Exception as e:
        app.logger.error(f'Ana sayfa yüklenirken hata oluştu: {str(e)}')
        flash(f'Bir hata oluştu: {str(e)}', 'error')
        return render_template('index.html', urunler=[])

@app.route('/urun_teslim_al/<int:urun_id>')
@login_required
def urun_teslim_al(urun_id):
    try:
        urun = Urun.query.get_or_404(urun_id)
        
        if urun.durum == 'Bekleme Alanında':
            flash('Bu ürün zaten bekleme alanında!', 'warning')
            return redirect(url_for('index'))
        
        eski_durum = urun.durum # Log için eski durumu yakala

        urun.durum = 'Bekleme Alanında'
        urun.teslim_alan = session.get('username')
        urun.teslim_alma_tarihi = datetime.utcnow()
        urun.hurda_tarihi = None # Hurda bilgilerini temizle
        urun.hurda_aciklama = None

        # Tüm ilişkili UrunLaboratuvar durumlarını 'Bekleme Alanında' olarak güncelle
        for lab_durum in urun.laboratuvar_durumlari:
            lab_durum.durum = 'Bekleme Alanında'
            lab_durum.hurda_tarihi = None
            lab_durum.hurda_aciklama = None
        
        db.session.commit()

        # Log kaydı oluştur
        log_entry = LogEntry(
            user_id=session['user_id'],
            username=session['username'],
            action=f'Ürün Teslim Alındı (Bekleme Alanına): {eski_durum} -> Bekleme Alanında',
            urun_id=urun_id,
            details=json.dumps({
                'seri_no': urun.seri_no,
                'eski_durum': eski_durum,
                'yeni_durum': 'Bekleme Alanında'
            })
        )
        db.session.add(log_entry)
        db.session.commit()

        logger.info(f"Ürün teslim alındı. Ürün ID: {urun_id}, Seri No: {urun.seri_no}, Teslim Alan Kullanıcı: {session.get('username')}")
        flash('Ürün başarıyla teslim alındı!', 'success')
    except Exception as e:
        flash(f'Hata oluştu: {str(e)}', 'error')
    return redirect(url_for('index'))

@app.route('/urun_ekle', methods=['POST'])
@login_required
def urun_ekle():
    try:
        print("[DEBUG] Ürün ekleme fonksiyonu BAŞLADI")
        logger.debug("[DEBUG] Ürün ekleme fonksiyonu BAŞLADI")
        is_admin = session.get('role') == 'admin'
        print(f'[DEBUG] Kullanıcı admin mi? {is_admin}')
        if not is_admin and request.form['isletme'] != session['isletme']:
            print("[DEBUG] Kullanıcı işletme yetkisi hatası")
            raise ValueError("Bu işletme için ürün ekleme yetkiniz yok!")
        isletme = request.form['isletme']
        model_no = request.form['model_no']
        seri_no = request.form['seri_no']
        jira_no = request.form['jira_no']
        secilen_laboratuvarlar = request.form.getlist('laboratuvarlar')
        aciklama = request.form.get('aciklama', '')
        print(f"[DEBUG] Formdan gelenler: isletme={isletme}, model_no={model_no}, seri_no={seri_no}, jira_no={jira_no}, laboratuvarlar={secilen_laboratuvarlar}")
        if not all([isletme, model_no, seri_no, jira_no]):
            print("[DEBUG] Zorunlu alanlar eksik!")
            raise ValueError("İşletme, Stok Numarası, Seri No ve Jira No zorunludur!")
        if not secilen_laboratuvarlar:
            print("[DEBUG] Laboratuvar seçilmedi")
            raise ValueError("En az bir laboratuvar seçilmelidir!")
        if Urun.query.filter_by(seri_no=seri_no).first():
            print("[DEBUG] Seri numarası zaten var")
            raise ValueError(f"'{seri_no}' seri numaralı ürün zaten mevcut!")
        gorsel_path = app.config['DEFAULT_LOGO_PATH']
        if 'gorsel' in request.files:
            file = request.files['gorsel']
            if file and file.filename:
                filename = secure_filename(file.filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                gorsel_path = os.path.join('static/images', filename)
                logger.debug(f"[DEBUG] Yüklenen görsel: {gorsel_path}")
        print(f"[DEBUG] Kullanılacak görsel: {gorsel_path}")
        yeni_urun = Urun(
            isletme=isletme,
            model_no=model_no,
            seri_no=seri_no,
            jira_no=jira_no,
            gorsel_path=gorsel_path,
            laboratuvarlar=','.join(secilen_laboratuvarlar) if secilen_laboratuvarlar else '',
            durum='Yolda',
            aciklama=aciklama
        )
        print("[DEBUG] Yeni ürün nesnesi oluşturuldu")
        db.session.add(yeni_urun)
        db.session.commit()
        print("[DEBUG] Yeni ürün veritabanına kaydedildi")
        print("[DEBUG] Commit sonrası ürün sayısı:", Urun.query.count())
        for lab in secilen_laboratuvarlar:
            lab_durum = UrunLaboratuvar(
                urun_id=yeni_urun.id,
                laboratuvar=lab,
                durum='Yolda',
                hurda_tarihi=None,
                hurda_aciklama=None
            )
            db.session.add(lab_durum)
        print("[DEBUG] Laboratuvar durumları eklendi")
        db.session.commit()
        print("[DEBUG] Laboratuvar durumları veritabanına kaydedildi")
        log_entry = LogEntry(
            user_id=session['user_id'],
            username=session['username'],
            action='Yeni Ürün Eklendi',
            urun_id=yeni_urun.id,
            details=json.dumps({
                'isletme': isletme,
                'model_no': model_no,
                'seri_no': seri_no,
                'jira_no': jira_no,
                'laboratuvarlar': secilen_laboratuvarlar,
                'gorsel_path': gorsel_path,
                'aciklama': aciklama
            })
        )
        db.session.add(log_entry)
        db.session.commit()
        print("[DEBUG] Log kaydı oluşturuldu ve kaydedildi")
        print(f"[DEBUG] Eklenen ürünün işletme adı: {yeni_urun.isletme}")
        print(f"[DEBUG] Oturumdaki işletme adı: {session.get('isletme')}")
        logger.info(f"Ürün başarıyla eklendi. Ürün ID: {yeni_urun.id}, Seri No: {yeni_urun.seri_no}, Ekleyen Kullanıcı: {session.get('username')}")
        flash('Ürün başarıyla eklendi!', 'success')
        return redirect(url_for('index'))
    except Exception as e:
        import traceback
        db.session.rollback()
        app.logger.error(f'[DEBUG] Ürün ekleme hatası: {str(e)}')
        print(f"[DEBUG] Ürün ekleme hatası: {str(e)}")
        print(traceback.format_exc())
        flash(str(e), 'error')
        return redirect(url_for('index'))

@app.route('/durum_degistir/<int:urun_id>/<yeni_durum>', methods=['POST'])
@login_required
def durum_degistir(urun_id, yeni_durum):
    try:
        urun = Urun.query.get_or_404(urun_id)
        eski_durum = urun.durum
        urun.durum = yeni_durum
        
        # Eğer yeni durum 'Hurda' ise hurda bilgilerini güncelle
        if yeni_durum == 'Hurda':
            urun.hurda_tarihi = datetime.utcnow()
            urun.hurda_aciklama = request.form.get('hurda_aciklama', 'Ürün manuel olarak hurdaya ayrıldı.')
        else:
            urun.hurda_tarihi = None
            urun.hurda_aciklama = None

        # Bekleme alanına geçişte veya Laboratuvarda geçişte laboratuvar ataması ve durum güncellemeleri
        if yeni_durum == 'Bekleme Alanında':
            urun.teslim_alan = session.get('username')
            urun.teslim_alma_tarihi = datetime.utcnow()
            # Tüm laboratuvar durumlarını 'Bekleme Alanında' olarak güncelle
            for lab_durum in urun.laboratuvar_durumlari:
                lab_durum.durum = 'Bekleme Alanında'
                lab_durum.hurda_tarihi = None
                lab_durum.hurda_aciklama = None
        elif yeni_durum == 'Laboratuvarda':
            # Eğer bekleme alanından veya yoldan laboratuvara geçiyorsa
            if eski_durum in ['Bekleme Alanında', 'Yolda']:
                for lab_durum in urun.laboratuvar_durumlari:
                    if lab_durum.durum != 'Hurda': # Hurda olmayanları laboratuvarda olarak işaretle
                        lab_durum.durum = 'Laboratuvarda'
                        lab_durum.hurda_tarihi = None
                        lab_durum.hurda_aciklama = None
            
        db.session.commit()

        # Log kaydı oluştur
        log_entry = LogEntry(
            user_id=session['user_id'],
            username=session['username'],
            action=f'Ürün Durumu Değiştirildi: {eski_durum} -> {yeni_durum}',
            urun_id=urun_id,
            details=json.dumps({
                'seri_no': urun.seri_no,
                'eski_durum': eski_durum,
                'yeni_durum': yeni_durum
            })
        )
        db.session.add(log_entry)
        db.session.commit()

        logger.info(f"Ürün durumu güncellendi. Ürün ID: {urun_id}, Eski Durum: {eski_durum}, Yeni Durum: {yeni_durum}, Güncelleyen Kullanıcı: {session.get('username')}")
        flash(f'Ürün durumu başarıyla güncellendi: {yeni_durum}', 'success')
        
        # URL parametrelerini koru
        params = {
            'lab': request.args.get('lab', 'all'),
            'isletme': request.args.get('isletme', 'all'),
            'durum': request.args.get('durum', 'all'),
            'show_hurda': request.args.get('show_hurda', 'false')
        }
        
        return redirect(url_for('index', **params))
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Durum değiştirme hatası: {str(e)}')
        flash('Durum değiştirilirken bir hata oluştu!', 'error')
        return redirect(url_for('index'))

@app.route('/laboratuvar_teslim_al/<int:urun_id>', methods=['POST'])
@login_required
def laboratuvar_teslim_al(urun_id):
    try:
        # Ürünü veritabanından bul
        urun = Urun.query.get_or_404(urun_id)
        
        # Laboratuvar seçimini kontrol et
        secilen_laboratuvarlar = request.form.getlist('laboratuvarlar')
        if not secilen_laboratuvarlar:
            flash('En az bir laboratuvar seçmelisiniz!', 'error')
            return redirect(url_for('index'))
        
        # Mevcut laboratuvar durumlarını temizle
        UrunLaboratuvar.query.filter_by(urun_id=urun.id).delete()
        
        # Yeni laboratuvar durumlarını ekle
        for lab in secilen_laboratuvarlar:
            lab_durum = UrunLaboratuvar(
                urun_id=urun.id,
                laboratuvar=lab,
                durum='Laboratuvarda' # Laboratuvara teslim edildiğinde direkt laboratuvarda olsun
            )
            db.session.add(lab_durum)
        
        # Ürün durumunu güncelle
        urun.laboratuvarlar = ','.join(secilen_laboratuvarlar)
        urun.durum = 'Laboratuvarda'
        
        # Hurda bilgilerini temizle
        urun.hurda_tarihi = None
        urun.hurda_aciklama = None
        
        # Değişiklikleri kaydet
        db.session.commit()

        # Log kaydı oluştur
        log_entry = LogEntry(
            user_id=session['user_id'],
            username=session['username'],
            action='Laboratuvara Teslim Edildi',
            urun_id=urun_id,
            details=json.dumps({
                'seri_no': urun.seri_no,
                'secilen_laboratuvarlar': secilen_laboratuvarlar
            })
        )
        db.session.add(log_entry)
        db.session.commit()
        
        logger.info(f"Ürün laboratuvara teslim edildi. Ürün ID: {urun_id}, Laboratuvarlar: {urun.laboratuvarlar}, Teslim Eden Kullanıcı: {session.get('username')}")
        flash(f'Ürün başarıyla laboratuvara teslim edildi.', 'success')
        
        # URL parametrelerini koru
        params = {
            'lab': request.args.get('lab', 'all'),
            'isletme': request.args.get('isletme', 'all'),
            'durum': request.args.get('durum', 'all'),
            'show_hurda': request.args.get('show_hurda', 'false')
        }
        
        return redirect(url_for('index', **params))
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Laboratuvar teslim alma hatası: {str(e)}')
        flash('Laboratuvar teslim alma sırasında bir hata oluştu!', 'error')
        return redirect(url_for('index'))

def get_filter_params():
    """URL parametrelerini al"""
    return {
        'model_no': request.args.get('model_no', ''),
        'seri_no': request.args.get('seri_no', ''),
        'jira_no': request.args.get('jira_no', ''),
        'durum': request.args.get('durum', ''),
        'lab': request.args.get('lab', ''),
        'isletme': request.args.get('isletme', ''),
        'show_in_transit': request.args.get('show_in_transit', 'false')
    }

@app.route('/urun_duzenle/<int:urun_id>', methods=['GET', 'POST'])
@login_required
def urun_duzenle(urun_id):
    global laboratuvarlar, isletmeler
    urun = Urun.query.get_or_404(urun_id)
    if request.method == 'GET':
        return render_template('urun_duzenle.html', urun=urun, isletmeler=isletmeler, laboratuvarlar=laboratuvarlar)
    try:
        app.logger.info(f'Ürün düzenleme başlatıldı. ID: {urun_id}')
        app.logger.debug(f'Form verisi: {request.form}')
        
        # Ürünü veritabanından bul
        urun = Urun.query.get_or_404(urun_id)
        app.logger.info(f'Ürün bulundu: {urun.model_no}')

        # Değişiklikleri izlemek için eski değerleri kaydet
        old_isletme = urun.isletme
        old_model_no = urun.model_no
        old_seri_no = urun.seri_no
        old_jira_no = urun.jira_no
        old_gorsel_path = urun.gorsel_path
        old_laboratuvarlar = urun.laboratuvarlar.split(',') if urun.laboratuvarlar else []
        
        # Form verilerini al
        model_no = request.form.get('model_no')
        seri_no = request.form.get('seri_no')
        jira_no = request.form.get('jira_no')
        laboratuvarlar = request.form.getlist('laboratuvarlar')
        
        app.logger.debug(f'Alınan veriler: model_no={model_no}, seri_no={seri_no}, jira_no={jira_no}, laboratuvarlar={laboratuvarlar}')
        
        if not all([model_no, seri_no, jira_no]):
            flash('Tüm zorunlu alanları doldurun!', 'error')
            return redirect(url_for('index', **get_filter_params()))
        
        # Seri numarası kontrolü (kendisi hariç)
        existing = Urun.query.filter(Urun.seri_no == seri_no, Urun.id != urun_id).first()
        if existing:
            flash(f"'{seri_no}' seri numaralı başka bir ürün zaten mevcut!", 'error')
            return redirect(url_for('index', **get_filter_params()))
        
        # Admin kullanıcılar için ek alanlar
        if session.get('role') == 'admin':
            isletme = request.form.get('isletme')
            if isletme:
                urun.isletme = isletme
                app.logger.info(f'İşletme güncellendi: {isletme}')
        
        # Temel bilgileri güncelle
        urun.model_no = model_no
        urun.seri_no = seri_no
        urun.jira_no = jira_no
        app.logger.info('Temel bilgiler güncellendi')
        
        # Görsel işleme
        if 'gorsel' in request.files:
            file = request.files['gorsel']
            if file and file.filename:
                app.logger.info(f'Yeni görsel yükleniyor: {file.filename}')
                
                # Eski görseli sil (varsayılan logo değilse)
                if urun.gorsel_path and not urun.gorsel_path.endswith('owl-logo.png'):
                    try:
                        old_path = os.path.join(app.root_path, urun.gorsel_path)
                        if os.path.exists(old_path):
                            os.remove(old_path)
                            app.logger.info('Eski görsel silindi')
                    except Exception as e:
                        app.logger.error(f'Eski görsel silinirken hata: {str(e)}')
                
                # Yeni görseli kaydet
                filename = secure_filename(file.filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                urun.gorsel_path = os.path.join('static/images', filename)
                app.logger.info('Yeni görsel kaydedildi')
            elif not urun.gorsel_path:  # Eğer mevcut görsel yoksa
                urun.gorsel_path = app.config['DEFAULT_LOGO_PATH']
                app.logger.info('Varsayılan logo atandı')
        
        # Laboratuvar bilgilerini güncelle
        if laboratuvarlar:
            # Önce mevcut laboratuvar durumlarını sil
            UrunLaboratuvar.query.filter_by(urun_id=urun.id).delete()
            
            # Yeni laboratuvar durumlarını ekle
            for lab in laboratuvarlar:
                lab_durum = UrunLaboratuvar(
                    urun_id=urun.id,
                    laboratuvar=lab,
                    durum='Yolda'
                )
                db.session.add(lab_durum)
            
            urun.laboratuvarlar = ','.join(laboratuvarlar)
            app.logger.info('Laboratuvar bilgileri güncellendi')
        
        db.session.commit()

        # Değişiklikleri detaylandırmak için yeni değerleri al
        new_details = {
            'isletme': urun.isletme,
            'model_no': urun.model_no,
            'seri_no': urun.seri_no,
            'jira_no': urun.jira_no,
            'gorsel_path': urun.gorsel_path,
            'laboratuvarlar': urun.laboratuvarlar.split(',') if urun.laboratuvarlar else [],
        }

        changed_fields = {}
        if old_isletme != new_details['isletme']:
            changed_fields['isletme'] = {'old': old_isletme, 'new': new_details['isletme']}
        if old_model_no != new_details['model_no']:
            changed_fields['model_no'] = {'old': old_model_no, 'new': new_details['model_no']}
        if old_seri_no != new_details['seri_no']:
            changed_fields['seri_no'] = {'old': old_seri_no, 'new': new_details['seri_no']}
        if old_jira_no != new_details['jira_no']:
            changed_fields['jira_no'] = {'old': old_jira_no, 'new': new_details['jira_no']}
        if old_gorsel_path != new_details['gorsel_path']:
            changed_fields['gorsel_path'] = {'old': old_gorsel_path, 'new': new_details['gorsel_path']}
        if set(old_laboratuvarlar) != set(new_details['laboratuvarlar']):
            changed_fields['laboratuvarlar'] = {'old': old_laboratuvarlar, 'new': new_details['laboratuvarlar']}

        if changed_fields: # Sadece değişiklik varsa log kaydı oluştur
            log_entry = LogEntry(
                user_id=session['user_id'],
                username=session['username'],
                action='Ürün Düzenlendi',
                urun_id=urun_id,
                details=json.dumps({
                    'seri_no': urun.seri_no,
                    'changes': changed_fields
                })
            )
            db.session.add(log_entry)
            db.session.commit()

        logger.info(f"Ürün başarıyla güncellendi. Ürün ID: {urun_id}, Seri No: {urun.seri_no}, Güncelleyen Kullanıcı: {session.get('username')}")
        flash('Ürün başarıyla güncellendi!', 'success')
        return redirect(url_for('index', **get_filter_params()))
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Ürün güncelleme hatası: {str(e)}')
        flash(str(e), 'error')
        return redirect(url_for('index', **get_filter_params()))

@app.route('/hurda/<int:urun_id>', methods=['POST'])
@login_required
def hurda_et(urun_id):
    try:
        urun = Urun.query.get_or_404(urun_id)
        if urun.durum not in ['Laboratuvarda', 'Bekleme Alanında']:
            raise ValueError("Bu ürün laboratuvarda veya bekleme alanında değil!")
            
        aciklama = request.form.get('hurda_aciklama')
        if not aciklama:
            raise ValueError("Hurda açıklaması gerekli!")
        
        # Tüm laboratuvar durumlarını hurda olarak işaretle
        for lab_durum in urun.laboratuvar_durumlari:
            lab_durum.durum = 'Hurda'
            lab_durum.hurda_tarihi = datetime.now()
            lab_durum.hurda_aciklama = aciklama
        # Ürünün genel durumunu hurda olarak güncelle
        urun.durum = 'Hurda'
        urun.hurda_aciklama = aciklama
        urun.hurda_tarihi = datetime.now()
        # Ürünün genel durumunu laboratuvarlara göre tekrar güncelle
        update_urun_durum_from_labs(urun)
        db.session.commit()

        # Log kaydı oluştur
        log_entry = LogEntry(
            user_id=session['user_id'],
            username=session['username'],
            action='Ürün Hurdaya Ayrıldı',
            urun_id=urun_id,
            details=json.dumps({
                'seri_no': urun.seri_no,
                'hurda_aciklama': aciklama
            })
        )
        db.session.add(log_entry)
        db.session.commit()

        logger.info(f"Ürün hurda olarak işaretlendi. Ürün ID: {urun_id}, Seri No: {urun.seri_no}, Açıklama: {aciklama}, İşaretleyen Kullanıcı: {session.get('username')}")
        flash(f"Ürün ve tüm laboratuvar durumları hurda olarak işaretlendi.", "success")
        return redirect(url_for('index'))
    except Exception as e:
        flash(str(e), "error")
        return redirect(url_for('index'))

@app.route('/bekleme_alani_yap/<int:urun_id>', methods=['POST'])
@login_required
def bekleme_alani_yap(urun_id):
    try:
        urun = Urun.query.get_or_404(urun_id)
        # Tüm laboratuvar durumlarını bekleme alanında olarak işaretle
        for lab_durum in urun.laboratuvar_durumlari:
            lab_durum.durum = 'Bekleme Alanında'
            lab_durum.hurda_tarihi = None
            lab_durum.hurda_aciklama = None
        urun.durum = 'Bekleme Alanında'
        urun.hurda_tarihi = None
        urun.hurda_aciklama = None
        urun.teslim_alan = session.get('username')
        urun.teslim_alma_tarihi = datetime.utcnow()
        db.session.commit()
        # Log kaydı oluştur
        log_entry = LogEntry(
            user_id=session['user_id'],
            username=session['username'],
            action='Ürün ve Laboratuvarlar Bekleme Alanına Alındı',
            urun_id=urun_id,
            details=json.dumps({
                'seri_no': urun.seri_no
            })
        )
        db.session.add(log_entry)
        db.session.commit()
        flash('Ürün ve tüm laboratuvarlar bekleme alanına alındı.', 'success')
    except Exception as e:
        flash(f'Hata oluştu: {str(e)}', 'error')
    return redirect(url_for('index'))

@app.route('/rapor')
@login_required
@admin_required
def rapor():
    try:
        # Filtreler kaldırıldı, tüm ürünler listelenecek
        urunler = Urun.query.order_by(Urun.gonderim_tarihi.desc()).all()
        # Laboratuvar listesini al
        laboratuvarlar = ['Gerilim Performans', 'Derating', 'İklimlendirme ve Titreşim', 
                         'EMC', 'Safety', 'IPC', 'Optik Performans', 'Dokunmatik Performans']
        return render_template('rapor.html', 
                             urunler=urunler,
                             laboratuvarlar=laboratuvarlar)
    except Exception as e:
        app.logger.error(f'Rapor oluşturulurken hata oluştu: {str(e)}')
        flash(f'Rapor oluşturulurken hata oluştu: {str(e)}', 'error')
        return redirect(url_for('index'))

@app.route('/gecmis')
@login_required
def gecmis():
    try:
        # Tüm log kayıtlarını al, en yeniden eskiye doğru sırala
        log_kayitlari = LogEntry.query.order_by(LogEntry.timestamp.desc()).all()
        return render_template('gecmis.html', log_kayitlari=log_kayitlari)
    except Exception as e:
        app.logger.error(f'Geçmiş raporu oluşturulurken hata oluştu: {str(e)}')
        flash(f'Geçmiş raporu oluşturulurken hata oluştu: {str(e)}', 'error')
        return redirect(url_for('index'))

@app.route('/laboratuvar_durum_degistir/<int:urun_id>/<laboratuvar>/<yeni_durum>', methods=['POST'])
@login_required
def laboratuvar_durum_degistir(urun_id, laboratuvar, yeni_durum):
    try:
        # Ürünü ve laboratuvar durumunu bul
        urun = Urun.query.get_or_404(urun_id)
        lab_durum = UrunLaboratuvar.query.filter_by(urun_id=urun_id, laboratuvar=laboratuvar).first_or_404()
        
        # Durumu güncelle
        lab_durum.durum = yeni_durum
        
        # Eğer bu laboratuvar 'Laboratuvarda' olduysa, diğerlerini 'Ürün Bekleniyor' yap
        if yeni_durum == 'Laboratuvarda':
            for diger_lab in urun.laboratuvar_durumlari:
                if diger_lab.laboratuvar != laboratuvar and diger_lab.durum != 'Hurda':
                    diger_lab.durum = 'Ürün Bekleniyor'
        
        # Eğer hurda durumuna geçiliyorsa, tarih ve açıklama ekle
        if yeni_durum == 'Hurda':
            lab_durum.hurda_tarihi = datetime.utcnow()
            lab_durum.hurda_aciklama = request.form.get('hurda_aciklama', 'Laboratuvar tarafından hurdaya ayrıldı.')
        # Eğer hurda durumundan çıkılıyorsa, tarih ve açıklamayı temizle
        elif yeni_durum != 'Hurda':
            lab_durum.hurda_tarihi = None
            lab_durum.hurda_aciklama = None
        
        # Check and update the main product status based on all assigned laboratories
        all_lab_statuses = [l.durum for l in urun.laboratuvar_durumlari]
        update_urun_durum_from_labs(urun)
        db.session.commit()

        # Log kaydı oluştur
        log_entry = LogEntry(
            user_id=session['user_id'],
            username=session['username'],
            action=f'Laboratuvar Durumu Değiştirildi: {laboratuvar} - {lab_durum.durum} -> {yeni_durum}',
            urun_id=urun_id,
            details=json.dumps({
                'seri_no': urun.seri_no,
                'laboratuvar': laboratuvar,
                'eski_durum': lab_durum.durum,
                'yeni_durum': yeni_durum
            })
        )
        db.session.add(log_entry)
        db.session.commit()
        
        logger.info(f"Laboratuvar durumu güncellendi. Ürün ID: {urun_id}, Laboratuvar: {laboratuvar}, Yeni Durum: {yeni_durum}, Güncelleyen Kullanıcı: {session.get('username')}")
        flash(f'{laboratuvar} laboratuvarı için durum başarıyla güncellendi.', 'success')
        return redirect(url_for('index', **get_filter_params()))
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Laboratuvar durum değiştirme hatası: {str(e)}')
        flash('Laboratuvar durumu değiştirilirken bir hata oluştu!', 'error')
        return redirect(url_for('index', **get_filter_params()))

@app.route('/urun_sil/<int:urun_id>', methods=['POST'])
@login_required
def urun_sil(urun_id):
    try:
        # Admin kontrolü
        if session.get('role') != 'admin':
            flash('Bu işlem için admin yetkisi gereklidir!', 'error')
            return redirect(url_for('index', **get_filter_params()))
        
        # Ürünü bul
        urun = Urun.query.get_or_404(urun_id)

        # Log için gerekli bilgileri silmeden önce al
        urun_seri_no_for_log = urun.seri_no
        urun_model_no_for_log = urun.model_no
        
        # Önce laboratuvar durumlarını sil
        UrunLaboratuvar.query.filter_by(urun_id=urun.id).delete()
        
        # Ürün görselini sil (eğer varsa ve varsayılan logo değilse)
        if urun.gorsel_path and not urun.gorsel_path.endswith('owl-logo.png'):
            try:
                file_path = os.path.join(app.root_path, urun.gorsel_path)
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception as e:
                app.logger.error(f'Görsel silinirken hata: {str(e)}')
        
        # Ürünü sil
        db.session.delete(urun)
        db.session.commit()

        # Log kaydı oluştur
        log_entry = LogEntry(
            user_id=session['user_id'],
            username=session['username'],
            action='Ürün Silindi',
            urun_id=urun_id,
            details=json.dumps({
                'seri_no': urun_seri_no_for_log,
                'model_no': urun_model_no_for_log
            })
        )
        db.session.add(log_entry)
        db.session.commit()
        
        logger.info(f"Ürün başarıyla silindi. Ürün ID: {urun_id}, Seri No: {urun_seri_no_for_log}, Silen Kullanıcı: {session.get('username')}")
        flash('Ürün başarıyla silindi.', 'success')
        return redirect(url_for('index', **get_filter_params()))
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Ürün silme hatası: {str(e)}')
        flash('Ürün silinirken bir hata oluştu!', 'error')
        return redirect(url_for('index', **get_filter_params()))

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/api/urun/<int:urun_id>')
def api_urun_detay(urun_id):
    urun = Urun.query.get_or_404(urun_id)
    return jsonify({
        'id': urun.id,
        'isletme': urun.isletme,
        'model_no': urun.model_no,
        'seri_no': urun.seri_no,
        'jira_no': urun.jira_no,
        'gorsel_path': urun.gorsel_path,
        'laboratuvarlar': [lab.laboratuvar for lab in urun.laboratuvar_durumlari],
        'durum': urun.durum,
        'teslim_alan': urun.teslim_alan,
        'teslim_alma_tarihi': urun.teslim_alma_tarihi.isoformat() if urun.teslim_alma_tarihi else None
    })

@app.route('/urun/<int:urun_id>')
def urun_detay(urun_id):
    try:
        urun = Urun.query.get_or_404(urun_id)
        # Paylaşım URL'sini oluştur
        if request.headers.get('X-Forwarded-Proto'):
            # Proxy arkasında çalışıyorsa
            base_url = request.headers.get('X-Forwarded-Proto') + '://' + request.headers.get('X-Forwarded-Host', request.host)
        else:
            # Direkt erişimde
            base_url = request.scheme + '://' + request.host
        
        share_url = urljoin(base_url, url_for('urun_detay', urun_id=urun_id))
        
        app.logger.debug(f'Oluşturulan paylaşım URL: {share_url}')

        # Ürüne ait log kayıtlarını al
        urun_log_kayitlari = LogEntry.query.filter_by(urun_id=urun.id).order_by(LogEntry.timestamp.desc()).all()

        return render_template('urun_detay.html', urun=urun, share_url=share_url, urun_log_kayitlari=urun_log_kayitlari)
    except Exception as e:
        app.logger.error(f'Ürün detay görüntüleme hatası: {str(e)}')
        flash('Ürün detayları görüntülenirken bir hata oluştu!', 'error')
        return redirect(url_for('index'))

@app.route('/update_laboratuvar_durum/<int:urun_laboratuvar_id>', methods=['POST'])
@login_required
def update_laboratuvar_durum(urun_laboratuvar_id):
    try:
        data = request.get_json()
        new_durum = data.get('durum')

        if not new_durum:
            return jsonify(success=False, message="Yeni durum belirtilmedi."), 400

        lab_durum_entry = UrunLaboratuvar.query.get_or_404(urun_laboratuvar_id)
        urun = Urun.query.get_or_404(lab_durum_entry.urun_id)

        old_durum = lab_durum_entry.durum
        lab_durum_entry.durum = new_durum

        # Update hurda_tarihi and hurda_aciklama based on new_durum
        if new_durum == 'Hurda':
            lab_durum_entry.hurda_tarihi = datetime.utcnow()
            # You might want to get hurda_aciklama from the frontend if needed
            lab_durum_entry.hurda_aciklama = "Laboratuvar tarafından hurdaya ayrıldı."
        else:
            lab_durum_entry.hurda_tarihi = None
            lab_durum_entry.hurda_aciklama = None

        # Check and update the main product status based on all assigned laboratories
        all_lab_statuses = [l.durum for l in urun.laboratuvar_durumlari]
        update_urun_durum_from_labs(urun)
        db.session.commit()

        # Log kaydı oluştur
        log_entry = LogEntry(
            user_id=session['user_id'],
            username=session['username'],
            action=f'Laboratuvar Durumu Güncellendi: {lab_durum_entry.laboratuvar} - {old_durum} -> {new_durum}',
            urun_id=urun.id,
            details=json.dumps({
                'seri_no': urun.seri_no,
                'laboratuvar': lab_durum_entry.laboratuvar,
                'eski_durum': old_durum,
                'yeni_durum': new_durum
            })
        )
        db.session.add(log_entry)
        db.session.commit()
        
        logger.info(f"Laboratuvar durumu güncellendi. Ürün ID: {urun.id}, Laboratuvar: {lab_durum_entry.laboratuvar}, Yeni Durum: {new_durum}, Güncelleyen Kullanıcı: {session.get('username')}")
        return jsonify(success=True, message="Laboratuvar durumu başarıyla güncellendi.")

    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Laboratuvar durumu güncelleme hatası: {str(e)}')
        return jsonify(success=False, message=str(e)), 500

def create_example_users():
    # Eğer hiç kullanıcı yoksa örnek kullanıcıları oluştur
    if not User.query.first():
        admin = User(username='admin', password='admin123', role='admin')
        ebi_user = User(username='ebi', password='ebi123', role='isletme', 
                       isletme='Eskişehir Buzdolabı İşletmesi')
        pci_user = User(username='pci', password='pci123', role='isletme', 
                       isletme='Bolu Pişirici Cihazlar İşletmesi')
        
        itt_user = User(username='itt', password='itt123', role='admin', isletme=None)
        gpt_user = User(username='gpt', password='gpt123', role='admin', isletme=None)
        emc_user = User(username='emc', password='emc123', role='admin', isletme=None)
        derating_user = User(username='derating', password='derating123', role='admin', isletme=None)
        safety_user = User(username='safety', password='safety123', role='admin', isletme=None)
        dokunmatik_user = User(username='dokunmatik', password='dokunmatik123', role='admin', isletme=None)
        
        db.session.add(admin)
        db.session.add(ebi_user)
        db.session.add(pci_user)
        db.session.add(itt_user)
        db.session.add(gpt_user)
        db.session.add(emc_user)
        db.session.add(derating_user)
        db.session.add(safety_user)
        db.session.add(dokunmatik_user)
        db.session.commit()
        logger.debug("Örnek kullanıcılar oluşturuldu")

def update_urun_durum_from_labs(urun):
    all_lab_statuses = [l.durum for l in urun.laboratuvar_durumlari]
    # Öncelik sırası: Hurda > Laboratuvarda > Transfer Edildi > Ürün Bekleniyor > Bekleme Alanında > Yolda
    if 'Hurda' in all_lab_statuses:
        urun.durum = 'Hurda'
        urun.hurda_tarihi = datetime.utcnow()
        urun.hurda_aciklama = 'Bir laboratuvar hurdaya ayrıldı.'
    elif 'Laboratuvarda' in all_lab_statuses:
        urun.durum = 'Laboratuvarda'
        urun.hurda_tarihi = None
        urun.hurda_aciklama = None
    elif 'Transfer Edildi' in all_lab_statuses:
        urun.durum = 'Transfer Edildi'
        urun.hurda_tarihi = None
        urun.hurda_aciklama = None
    elif 'Ürün Bekleniyor' in all_lab_statuses:
        urun.durum = 'Ürün Bekleniyor'
        urun.hurda_tarihi = None
        urun.hurda_aciklama = None
    elif 'Bekleme Alanında' in all_lab_statuses:
        urun.durum = 'Bekleme Alanında'
        urun.hurda_tarihi = None
        urun.hurda_aciklama = None
    elif 'Yolda' in all_lab_statuses:
        urun.durum = 'Yolda'
        urun.hurda_tarihi = None
        urun.hurda_aciklama = None
    else:
        urun.durum = 'Bekleme Alanında'
        urun.hurda_tarihi = None
        urun.hurda_aciklama = None

if __name__ == '__main__':
    with app.app_context():
        # Veritabanını oluştur
        db.create_all()
        try:
            print('Tablolar:', db.engine.table_names())
        except Exception as e:
            print('Tablo isimleri alınamadı:', str(e))
        # Örnek kullanıcıları oluştur
        create_example_users()
    
    app.run(debug=True, host='0.0.0.0', port=5003)
