import streamlit as st
import pandas as pd
import sqlite3
import io
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh
import pytz

# --- DB & Timezone ---
tz = pytz.timezone("Europe/Istanbul")
conn = sqlite3.connect("personel.db", check_same_thread=False)
c = conn.cursor()

# --- Tablolar ---
c.execute("""
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    password TEXT,
    role TEXT,
    approved INTEGER
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS logs (
    username TEXT,
    durum TEXT,
    giris TEXT,
    cikis TEXT,
    sure INTEGER
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS notifications (
    username TEXT,
    message TEXT,
    created TEXT
)
""")
conn.commit()

# --- Admin hesabı ---
c.execute("""
INSERT OR IGNORE INTO users (username, password, role, approved)
VALUES (?, ?, ?, ?)
""", ("admin", "1234", "Yönetici", 1))
conn.commit()

# --- UI ---
st.set_page_config(page_title="Personel Yönetim Sistemi", page_icon="🏢", layout="wide")
st.markdown("<h1 style='text-align:center;color:#0A3D62;'>🏢 Personel Yönetim Sistemi</h1>", unsafe_allow_html=True)
st.markdown("---")

# --- Session State ---
if "role" not in st.session_state:
    st.session_state.role = None
if "user" not in st.session_state:
    st.session_state.user = None
if "login_time" not in st.session_state:
    st.session_state.login_time = None

# --- Login / Register ---
tab_login, tab_register = st.tabs(["🔑 Giriş Yap", "📝 Kayıt Ol"])

with tab_login:
    username = st.text_input("Kullanıcı Adı")
    password = st.text_input("Şifre", type="password")

    if st.button("Giriş"):
        user = c.execute(
            "SELECT * FROM users WHERE username=? AND password=?",
            (username, password)
        ).fetchone()

        if user:
            if user[3] == 1:
                st.session_state.user = user[0]
                st.session_state.role = user[2]
                st.session_state.login_time = datetime.now(tz)
                st.success("Giriş başarılı ✅")
            else:
                st.error("Hesabınız admin onayı bekliyor ❌")
        else:
            st.error("Hatalı kullanıcı adı veya şifre ❌")

with tab_register:
    new_user = st.text_input("Yeni Kullanıcı Adı")
    new_pass = st.text_input("Yeni Şifre", type="password")

    if st.button("Kayıt Ol"):
        if new_user and new_pass:
            try:
                c.execute("""
                    INSERT INTO users (username, password, role, approved)
                    VALUES (?, ?, ?, ?)
                """, (new_user, new_pass, "Personel", 0))
                conn.commit()
                st.success("Kayıt oluşturuldu ✅ (Admin onayı bekleniyor)")
            except sqlite3.IntegrityError:
                st.error("Bu kullanıcı adı zaten var ❌")
        else:
            st.error("Alanlar boş olamaz ❌")

# --- 15 dk uyarı ---
if st.session_state.login_time:
    if datetime.now(tz) - st.session_state.login_time > timedelta(minutes=15):
        st.warning("⏰ 15 dakika oldu!")

# =========================================================
# ===================== PERSONEL ==========================
# =========================================================
if st.session_state.role == "Personel":
    st.markdown("## 👤 Personel Paneli")

    tab1, tab2, tab3 = st.tabs(
        ["Durum Güncelle", "Şu An Dışarıda Olanlar", "Profilim"]
    )

    with tab1:
        durum = st.selectbox("Durumunuz", ["İçeriye Gir", "Dışarıya Çık"])

        if st.button("Kaydet"):
            now = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

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
                    """, (now, now, last_exit[0]))
                else:
                    c.execute("""
                        INSERT INTO logs (username, durum, giris)
                        VALUES (?, 'İçeride', ?)
                    """, (st.session_state.user, now))
            else:
                c.execute("""
                    INSERT INTO logs (username, durum, cikis)
                    VALUES (?, 'Dışarıda', ?)
                """, (st.session_state.user, now))

            conn.commit()
            st.success("Durum güncellendi ✅")

    with tab2:
        st_autorefresh(interval=10000, key="refresh")
        df_out = pd.read_sql("""
            SELECT username, cikis FROM logs
            WHERE durum='Dışarıda'
            ORDER BY cikis DESC
        """, conn)

        if df_out.empty:
            st.success("Kimse dışarıda değil")
        else:
            for _, r in df_out.iterrows():
                st.info(f"🚶 {r.username} (çıkış: {r.cikis})")

    with tab3:
        df_profile = pd.read_sql(
            "SELECT * FROM logs WHERE username=?",
            conn,
            params=(st.session_state.user,)
        )
        st.dataframe(df_profile, use_container_width=True)

        notif = pd.read_sql("""
            SELECT * FROM notifications
            WHERE username=?
            ORDER BY created DESC
        """, conn, params=(st.session_state.user,))

        for _, n in notif.iterrows():
            st.warning(f"📢 {n.message} ({n.created})")

# =========================================================
# ===================== YÖNETİCİ ==========================
# =========================================================
elif st.session_state.role == "Yönetici":
    st.markdown("## 👨‍💼 Yönetici Paneli")

    df = pd.read_sql("SELECT * FROM logs", conn)
    tab1, tab2, tab3, tab4 = st.tabs(
        ["Dashboard", "Loglar", "Kullanıcı Onayı", "Bildirim Gönder"]
    )

    with tab1:
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Toplam Personel", df.username.nunique())
        col2.metric("İçeride", df[df.durum == "İçeride"].username.nunique())
        col3.metric("Dışarıda", df[df.durum == "Dışarıda"].username.nunique())
        col4.metric("Ortalama Süre (dk)", round(df.sure.dropna().mean() or 0, 1))

    with tab2:
        st.dataframe(df, use_container_width=True)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False)
        st.download_button(
            "📥 Excel indir",
            output.getvalue(),
            "personel_logs.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    with tab3:
        pending = pd.read_sql(
            "SELECT username FROM users WHERE approved=0",
            conn
        )

        for _, r in pending.iterrows():
            if st.button(f"Onayla: {r.username}"):
                c.execute(
                    "UPDATE users SET approved=1 WHERE username=?",
                    (r.username,)
                )
                conn.commit()
                st.success(f"{r.username} onaylandı")

        df_users = pd.read_sql("SELECT * FROM users", conn)
        st.subheader("👥 Kullanıcılar")
        st.dataframe(df_users, use_container_width=True)

    with tab4:
        users_list = pd.read_sql(
            "SELECT username FROM users WHERE role='Personel'",
            conn
        )["username"].tolist()

        target = st.selectbox("Kullanıcı", users_list)
        msg = st.text_area("Mesaj")

        if st.button("Gönder"):
            c.execute("""
                INSERT INTO notifications (username, message, created)
                VALUES (?, ?, ?)
            """, (target, msg, datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
            st.success("Bildirim gönderildi ✅")
