// Firebase yapılandırması ve başlatma
import { initializeApp } from "https://www.gstatic.com/firebasejs/9.22.0/firebase-app.js";
import { getAuth, signInWithEmailAndPassword, createUserWithEmailAndPassword, signOut, onAuthStateChanged } from "https://www.gstatic.com/firebasejs/9.22.0/firebase-auth.js";
import { getFirestore, collection, addDoc, getDocs, doc, updateDoc, deleteDoc } from "https://www.gstatic.com/firebasejs/9.22.0/firebase-firestore.js";
import { getStorage, ref, uploadBytes, getDownloadURL } from "https://www.gstatic.com/firebasejs/9.22.0/firebase-storage.js";
import { getAnalytics } from "https://www.gstatic.com/firebasejs/9.22.0/firebase-analytics.js";

// Firebase yapılandırması
const firebaseConfig = {
  apiKey: "AIzaSyC-Zl-f0xAyFNrz_ccYo1XtHwnVGNpd8JI",
  authDomain: "tobed-hw.firebaseapp.com",
  projectId: "tobed-hw",
  storageBucket: "tobed-hw.firebasestorage.app",
  messagingSenderId: "90863126066",
  appId: "1:90863126066:web:a98abbd9cec392b03c5e2b",
  measurementId: "G-KPRQ1ZDPBC"
};

// Firebase başlatma
const app = initializeApp(firebaseConfig);
const auth = getAuth(app);
const db = getFirestore(app);
const storage = getStorage(app);
const analytics = getAnalytics(app);

// Firebase servisleri dışa aktarma
window.firebaseAuth = auth;
window.firebaseDb = db;
window.firebaseStorage = storage;
window.firebaseAnalytics = analytics;

// Auth fonksiyonları
window.firebaseSignIn = signInWithEmailAndPassword;
window.firebaseSignUp = createUserWithEmailAndPassword;
window.firebaseSignOut = signOut;
window.firebaseOnAuthStateChanged = onAuthStateChanged;

// Firestore fonksiyonları
window.firestoreCollection = collection;
window.firestoreAddDoc = addDoc;
window.firestoreGetDocs = getDocs;
window.firestoreDoc = doc;
window.firestoreUpdateDoc = updateDoc;
window.firestoreDeleteDoc = deleteDoc;

// Storage fonksiyonları
window.storageRef = ref;
window.storageUploadBytes = uploadBytes;
window.storageGetDownloadURL = getDownloadURL;

console.log('Firebase başarıyla yapılandırıldı!'); 