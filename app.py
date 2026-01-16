import streamlit as st
import pandas as pd
import sqlite3
import io
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh
import pytz

tz = pytz.timezone("Europe/Istanbul")
conn = sqlite3.connect("personel.db", check_same_thread=False)
c = conn.cursor()

# Tablolar
c.execute("""CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    password TEXT,
    role TEXT,
    approved INTEGER
)""")
c.execute("""CREATE TABLE IF NOT EXISTS logs (
    username TEXT,
    durum TEXT,
    giris TEXT,
    cikis TEXT,
    sure INTEGER
)""")
c.execute("""CREATE TABLE IF NOT EXISTS notifications (
    username TEXT,
    message TEXT,
    created TEXT
)""")
conn.commit()

# Admin hesabı
c.execute("INSERT OR IGNORE INTO users (username, password, role, approved) VALUES (?, ?, ?, ?)",
          ("admin", "1234", "Yönetici", 1))
conn.commit()

# --- Kurumsal Tema ve Başlık ---
st.set_page_config(page_title="Personel Yönetim Sistemi", page_icon="🏢", layout="wide")
st.markdown("<h1 style='text-align:center; color:#0A3D62;'>🏢 Personel Yönetim Sistemi</h1>", unsafe_allow_html=True)
st.markdown("---")

# --- Session State ---
if "role" not in st.session_state:
    st.session_state.role = None
if "login_time" not in st.session_state:
    st.session_state.login_time = None

# --- Giriş/Kayıt Paneli ---
tab_login, tab_register = st.tabs(["🔑 Giriş Yap", "📝 Kayıt Ol"])

with tab_login:
    username = st.text_input("Kullanıcı Adı")
    password = st.text_input("Şifre", type="password")
    if st.button("Giriş"):
        user = c.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password)).fetchone()
        if user:
            if user[3] == 1:
                st.session_state.role = user[2]
                st.session_state.user = user[0]
                st.session_state.login_time = datetime.now(tz)
                st.success("Giriş başarılı ✅")
            else:
                st.error("Hesabınız henüz admin tarafından onaylanmadı ❌")
        else:
            st.error("Hatalı kullanıcı adı veya şifre ❌")

with tab_register:
    new_user = st.text_input("Yeni Kullanıcı Adı")
    new_pass = st.text_input("Yeni Şifre", type="password")
    if st.button("Kayıt Ol"):
        if new_user and new_pass:
            try:
                c.execute("INSERT INTO users (username, password, role, approved) VALUES (?, ?, ?, ?)",
                          (new_user, new_pass, "Personel", 0))
                conn.commit()
                st.success("Kullanıcı oluşturuldu ✅ (Admin onayı bekleniyor)")
            except sqlite3.IntegrityError:
                st.error("Bu kullanıcı adı zaten mevcut ❌")
        else:
            st.error("Kullanıcı adı ve şifre boş olamaz ❌")

if st.session_state.get("login_time"):
    elapsed = datetime.now(tz) - st.session_state.login_time
    if elapsed > timedelta(minutes=15):
        st.warning("⏰ 15 dakika oldu, lütfen kontrol edin!")

# --- Personel Paneli ---
if st.session_state.get("role") == "Personel":
    st.markdown("## 👤 Personel Paneli")
    tab1, tab2, tab3 = st.tabs(["Durum Güncelle", "Şu An Dışarıda Olanlar", "Profilim"])

    with tab1:
        durum = st.selectbox("Durumunuz", ["İçeriye Gir", "Dışarıya Çık"])
        if st.button("Kaydet"):
            if durum == "İçeriye Gir":
                last_exit = c.execute("""
                    SELECT rowid, cikis FROM logs
                    WHERE username=? AND durum='Dışarıda'
                    ORDER BY cikis DESC LIMIT 1
                """, (st.session_state.user,)).fetchone()
                if last_exit:
                    c.execute("""
                        UPDATE logs
                        SET durum='İçeride',
                            giris=?,
                            sure=ROUND((JULIANDAY(?) - JULIANDAY(cikis)) * 24 * 60)
                        WHERE rowid=?
                    """, (datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S"),
                          datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S"),
                          last_exit[0]))
                else:
                    c.execute("INSERT INTO logs (username, durum, giris, cikis, sure) VALUES (?, ?, ?, ?, ?)",
                              (st.session_state.user, "İçeride", datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S"), None, None))
            else:
                c.execute("INSERT INTO logs (username, durum, giris, cikis, sure) VALUES (?, ?, ?, ?, ?)",
                          (st.session_state.user, "Dışarıda", None, datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S"), None))
            conn.commit()
            st.success("Durumunuz güncellendi ✅")

    with tab2:
        st_autorefresh(interval=10000, key="refresh")
        disaridaki = pd.read_sql("SELECT username, cikis FROM logs WHERE durum='Dışarıda' ORDER BY cikis DESC", conn)
        if not disaridaki.empty:
            for _, row in disaridaki.iterrows():
                st.info(f"🚶 {row['username']} şu anda dışarıda (çıkış: {row['cikis']})")
        else:
            st.success("Şu anda kimse dışarıda değil.")

    with tab3:
        profil = pd.read_sql("SELECT * FROM logs WHERE username=?", conn, params=(st.session_state.user,))
        if not profil.empty:
            st.dataframe(profil, use_container_width=True)
        else:
            st.info("Henüz log kaydınız yok.")

        # Bildirim kontrol
        notif = pd.read_sql("SELECT * FROM notifications WHERE username=? ORDER BY created DESC", conn, params=(st.session_state.user,))
        if not notif.empty:
            for _, row in notif.iterrows():
                st.warning(f"📢 Yönetici çağırıyor: {row['message']} (tarih: {row['created']})")

# --- Yönetici Paneli ---
elif st.session_state.get("role") == "Yönetici":
    st.markdown("## 👨‍💼 Yönetici Paneli")
    df = pd.read_sql("SELECT * FROM logs", conn)

    tab1, tab2, tab3, tab4 = st.tabs(["Dashboard", "Loglar", "Kullanıcı Onayı", "Bildirim Gönder"])

    with tab1:
        toplam = df["username"].nunique()
        icerde = df[(df["durum"]=="İçeride")]["username"].nunique()
        disarda = df[(df["durum"]=="Dışarıda")]["username"].nunique()
        ort_sure = df["sure"].dropna().mean()

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Toplam Personel", toplam)
        col2.metric("İçeride", icerde)
        col3.metric("Dışarıda (aktif)", disarda)
        col4.metric("Ortalama Süre (dk)", round(ort_sure,1) if not pd.isna(ort_sure) else 0)

    with tab2:
        st.dataframe(df, use_container_width=True)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Logs")
        excel_data = output.getvalue()
        st.download_button(
            label="📥 Excel Olarak İndir",
            data=excel_data,
            file_name="personel_logs.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    with tab3:
        pending = pd.read_sql("SELECT username FROM users WHERE approved=0", conn)
        if not pending.empty:
            st.warning("Onay bekleyen kullanıcılar:")
            for _, row in pending.iterrows():
                if st.button(f"Onayla: {row['username']}"):
                    c.execute("UPDATE users SET approved=1 WHERE username=?", (row['username'],))
                    conn.commit()
                    st.success(f"{row['username']} onaylandı ✅")
        else:
            st.success("Onay bekleyen kullanıcı yok")
                               df_users = pd.read_sql("SELECT * FROM users", conn)
        st.subheader("👥 Kullanıcı Tablosu")
        st.dataframe(df_users, use_container_width=True)

    with tab4:
        st.subheader("📢 Bildirim Gönder")
        # Admin için dropdown ile kullanıcı seçimi
        users_list = pd.read_sql("SELECT username FROM users WHERE role='Personel'", conn)["username"].tolist()
        target_user = st.selectbox("Kime bildirim göndereceksiniz?", users_list)
        message = st.text_area("Mesaj")
        if st.button("Gönder"):
            if target_user and message:
                c.execute("INSERT INTO notifications (username, message, created) VALUES (?, ?, ?)",
                          (target_user, message, datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")))
                conn.commit()
                st.success(f"{target_user} kullanıcısına bildirim gönderildi ✅")
            else:
                st.error("Kullanıcı adı ve mesaj boş olamaz ❌")


