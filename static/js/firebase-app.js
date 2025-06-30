// Firebase entegrasyonu ile uygulama fonksiyonları

// Sayfa yüklendikten sonra Firebase hazır olana kadar bekle
document.addEventListener('DOMContentLoaded', function() {
    // Firebase yüklenmesini bekle
    const checkFirebase = setInterval(() => {
        if (window.firebaseAuth && window.firebaseDb) {
            clearInterval(checkFirebase);
            initializeFirebaseApp();
        }
    }, 100);
});

function initializeFirebaseApp() {
    console.log('Firebase entegrasyonu başlatılıyor...');
    
    // Auth state değişikliklerini dinle
    window.firebaseOnAuthStateChanged(window.firebaseAuth, (user) => {
        if (user) {
            console.log('Kullanıcı giriş yapmış:', user.email);
            updateUIForLoggedInUser(user);
        } else {
            console.log('Kullanıcı çıkış yapmış');
            updateUIForLoggedOutUser();
        }
    });
}

// Firebase Auth ile giriş yapma
async function signInWithFirebase(email, password) {
    try {
        const userCredential = await window.firebaseSignIn(window.firebaseAuth, email, password);
        console.log('Firebase giriş başarılı:', userCredential.user.email);
        
        // Analytics'e event gönder
        if (window.firebaseAnalytics) {
            // Analytics event gönderme (opsiyonel)
        }
        
        return { success: true, user: userCredential.user };
    } catch (error) {
        console.error('Firebase giriş hatası:', error);
        return { success: false, error: error.message };
    }
}

// Firebase Auth ile kayıt olma
async function signUpWithFirebase(email, password) {
    try {
        const userCredential = await window.firebaseSignUp(window.firebaseAuth, email, password);
        console.log('Firebase kayıt başarılı:', userCredential.user.email);
        return { success: true, user: userCredential.user };
    } catch (error) {
        console.error('Firebase kayıt hatası:', error);
        return { success: false, error: error.message };
    }
}

// Firebase Auth ile çıkış yapma
async function signOutFromFirebase() {
    try {
        await window.firebaseSignOut(window.firebaseAuth);
        console.log('Firebase çıkış başarılı');
        return { success: true };
    } catch (error) {
        console.error('Firebase çıkış hatası:', error);
        return { success: false, error: error.message };
    }
}

// Firestore'a ürün kaydetme
async function saveProductToFirestore(productData) {
    try {
        const docRef = await window.firestoreAddDoc(
            window.firestoreCollection(window.firebaseDb, 'products'), 
            {
                ...productData,
                createdAt: new Date(),
                updatedAt: new Date()
            }
        );
        console.log('Ürün Firestore\'a kaydedildi:', docRef.id);
        return { success: true, id: docRef.id };
    } catch (error) {
        console.error('Firestore kayıt hatası:', error);
        return { success: false, error: error.message };
    }
}

// Firestore'dan ürünleri getirme
async function getProductsFromFirestore() {
    try {
        const querySnapshot = await window.firestoreGetDocs(
            window.firestoreCollection(window.firebaseDb, 'products')
        );
        
        const products = [];
        querySnapshot.forEach((doc) => {
            products.push({ id: doc.id, ...doc.data() });
        });
        
        console.log('Firestore\'dan ürünler getirildi:', products.length);
        return { success: true, products };
    } catch (error) {
        console.error('Firestore okuma hatası:', error);
        return { success: false, error: error.message };
    }
}

// Firebase Storage'a resim yükleme
async function uploadImageToFirebaseStorage(file, fileName) {
    try {
        const storageRef = window.storageRef(window.firebaseStorage, `images/${fileName}`);
        const snapshot = await window.storageUploadBytes(storageRef, file);
        const downloadURL = await window.storageGetDownloadURL(snapshot.ref);
        
        console.log('Resim Firebase Storage\'a yüklendi:', downloadURL);
        return { success: true, url: downloadURL };
    } catch (error) {
        console.error('Storage yükleme hatası:', error);
        return { success: false, error: error.message };
    }
}

// UI güncellemeleri
function updateUIForLoggedInUser(user) {
    // Giriş yapan kullanıcı için UI güncelleme
    const userEmailElements = document.querySelectorAll('.user-email');
    userEmailElements.forEach(element => {
        element.textContent = user.email;
    });
}

function updateUIForLoggedOutUser() {
    // Çıkış yapan kullanıcı için UI güncelleme
    const userEmailElements = document.querySelectorAll('.user-email');
    userEmailElements.forEach(element => {
        element.textContent = '';
    });
}

// Mevcut updateLaboratuvarDurum fonksiyonunu Firebase ile entegre et
function updateLaboratuvarDurum(urunLaboratuvarId, newDurum) {
    // Form data oluştur
    const formData = new FormData();
    formData.append('yeni_durum', newDurum);
    
    // Flask backend'e gönder
    fetch(`/laboratuvar_durum_guncelle/${urunLaboratuvarId}`, {
        method: 'POST',
        body: formData
    })
    .then(response => {
        if (response.ok) {
            console.log('Durum başarıyla güncellendi');
            
            // Firebase'e de kaydet (opsiyonel - senkronizasyon için)
            syncLaboratoryStatusToFirebase(urunLaboratuvarId, newDurum);
            
            location.reload();
        } else {
            console.error('Durum güncellenirken hata oluştu');
            alert('Durum güncellenemedi. Lütfen tekrar deneyin.');
        }
    })
    .catch(error => {
        console.error('Fetch hatası:', error);
        alert('Bir hata oluştu. Lütfen tekrar deneyin.');
    });
}

// Laboratuvar durumunu Firebase'e senkronize et
async function syncLaboratoryStatusToFirebase(urunLaboratuvarId, newDurum) {
    try {
        await window.firestoreAddDoc(
            window.firestoreCollection(window.firebaseDb, 'laboratuvar_logs'), 
            {
                urunLaboratuvarId: urunLaboratuvarId,
                newDurum: newDurum,
                timestamp: new Date(),
                source: 'web_app'
            }
        );
        console.log('Laboratuvar durumu Firebase\'e senkronize edildi');
    } catch (error) {
        console.error('Firebase senkronizasyon hatası:', error);
    }
}

// Firebase fonksiyonlarını global olarak erişilebilir yap
window.firebaseApp = {
    signIn: signInWithFirebase,
    signUp: signUpWithFirebase,
    signOut: signOutFromFirebase,
    saveProduct: saveProductToFirestore,
    getProducts: getProductsFromFirestore,
    uploadImage: uploadImageToFirebaseStorage
}; 