import os
import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://api:8000")

st.set_page_config(page_title="CliniQ", page_icon="🏥", layout="wide")

if "token" not in st.session_state:
    st.session_state.token = None
if "username" not in st.session_state:
    st.session_state.username = None
if "role" not in st.session_state:
    st.session_state.role = None
if "messages" not in st.session_state:
    st.session_state.messages = []


def api(method: str, path: str, **kwargs):
    headers = kwargs.pop("headers", {})
    if st.session_state.token:
        headers["Authorization"] = f"Bearer {st.session_state.token}"
    try:
        res = requests.request(method, f"{API_URL}{path}", headers=headers, timeout=120, **kwargs)
        return res
    except requests.exceptions.ConnectionError:
        st.error("Cannot reach the API. Is the backend running?")
        return None


# ── Auth page ─────────────────────────────────────────────────────────────────
def auth_page():
    st.title("CliniQ — Assistant d'aide à la décision clinique")
    st.markdown("---")

    tab_login, tab_register = st.tabs(["Connexion", "Créer un compte"])

    with tab_login:
        with st.form("login_form"):
            username = st.text_input("Nom d'utilisateur")
            password = st.text_input("Mot de passe", type="password")
            submitted = st.form_submit_button("Se connecter", use_container_width=True)
        if submitted:
            res = api("POST", "/login", json={"username": username, "password": password})
            if res and res.status_code == 200:
                st.session_state.token = res.json()["access_token"]
                me = api("GET", "/me")
                if me and me.status_code == 200:
                    st.session_state.username = me.json()["username"]
                    st.session_state.role = me.json()["role"]
                st.rerun()
            elif res:
                st.error("Identifiants incorrects.")

    with tab_register:
        with st.form("register_form"):
            new_username = st.text_input("Nom d'utilisateur")
            new_email = st.text_input("Email (optionnel)")
            new_password = st.text_input("Mot de passe", type="password")
            submitted = st.form_submit_button("Créer le compte", use_container_width=True)
        if submitted:
            res = api("POST", "/register", json={
                "username": new_username,
                "email": new_email or None,
                "password": new_password,
            })
            if res and res.status_code == 201:
                st.success("Compte créé. Vous pouvez vous connecter.")
            elif res:
                detail = res.json().get("detail") or res.json().get("error", "Erreur inconnue.")
                st.error(detail)


# ── Shared sidebar ────────────────────────────────────────────────────────────
def sidebar():
    with st.sidebar:
        st.title("CliniQ 🏥")
        st.markdown(f"**Utilisateur :** {st.session_state.username}")
        st.markdown(f"**Rôle :** {st.session_state.role}")
        st.markdown("---")
        if st.button("Se déconnecter", use_container_width=True):
            st.session_state.token = None
            st.session_state.username = None
            st.session_state.role = None
            st.session_state.messages = []
            st.rerun()


# ── Chat tab ──────────────────────────────────────────────────────────────────
def chat_tab():
    SPECIALTIES = [
        "", "Médecine Adulte", "Pédiatrie", "Gynécologie-Obstétrique",
        "Chirurgie", "Psychiatrie", "Urgences",
    ]
    specialty = st.selectbox(
        "Filtrer par spécialité",
        SPECIALTIES,
        format_func=lambda x: x if x else "Toutes les spécialités",
    )

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg["role"] == "assistant" and msg.get("sources"):
                with st.expander(f"Sources ({len(msg['sources'])})"):
                    for s in msg["sources"]:
                        st.markdown(
                            f"**{s.get('specialty', '')}** — {s.get('protocol', '')} "
                            f"/ {s.get('section_header', '')} "
                            f"(score: {s.get('score', 0):.2f})"
                        )

    question = st.chat_input("Ex: Quel est le protocole pour une détresse respiratoire ?")
    if question:
        st.session_state.messages.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)
        with st.chat_message("assistant"):
            with st.spinner("Recherche en cours..."):
                res = api("POST", "/query", json={
                    "question": question,
                    "specialty": specialty or None,
                })
            if res and res.status_code == 200:
                data = res.json()
                st.markdown(data["answer"])
                sources = data.get("sources", [])
                if sources:
                    with st.expander(f"Sources ({len(sources)})"):
                        for s in sources:
                            st.markdown(
                                f"**{s.get('specialty', '')}** — {s.get('protocol', '')} "
                                f"/ {s.get('section_header', '')} "
                                f"(score: {s.get('score', 0):.2f})"
                            )
                st.caption(f"Temps de réponse : {data['response_time_ms']:.0f} ms")
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": data["answer"],
                    "sources": sources,
                })
            elif res:
                err = res.json().get("error", "Erreur inconnue.")
                st.error(err)
                st.session_state.messages.append({"role": "assistant", "content": f"Erreur : {err}"})


# ── My history tab ────────────────────────────────────────────────────────────
def my_history_tab():
    if st.button("Actualiser"):
        st.rerun()
    res = api("GET", "/history")
    if res and res.status_code == 200:
        history = res.json()
        if not history:
            st.info("Aucune interaction enregistrée.")
        else:
            for item in history:
                with st.expander(
                    f"🕐 {item['created_at'][:19].replace('T', ' ')}  —  {item['question'][:80]}"
                ):
                    st.markdown(f"**Question :** {item['question']}")
                    if item.get("specialty"):
                        st.markdown(f"**Spécialité :** {item['specialty']}")
                    st.markdown(f"**Réponse :** {item['answer']}")
                    st.caption(f"Temps de réponse : {item['response_time_ms']:.0f} ms")


# ── Admin: all history tab ────────────────────────────────────────────────────
def all_history_tab():
    if st.button("Actualiser", key="refresh_all_history"):
        st.rerun()
    res = api("GET", "/admin/history")
    if res and res.status_code == 200:
        history = res.json()
        if not history:
            st.info("Aucune interaction enregistrée.")
        else:
            for item in history:
                with st.expander(
                    f"🕐 {item['created_at'][:19].replace('T', ' ')}  —  {item['question'][:80]}"
                ):
                    st.markdown(f"**Question :** {item['question']}")
                    if item.get("specialty"):
                        st.markdown(f"**Spécialité :** {item['specialty']}")
                    st.markdown(f"**Réponse :** {item['answer']}")
                    st.caption(f"Temps de réponse : {item['response_time_ms']:.0f} ms")


# ── Admin: user management tab ────────────────────────────────────────────────
def user_management_tab():
    if st.button("Actualiser", key="refresh_users"):
        st.rerun()
    res = api("GET", "/admin/users")
    if not res or res.status_code != 200:
        st.error("Impossible de charger les utilisateurs.")
        return

    users = res.json()
    for user in users:
        col1, col2, col3, col4 = st.columns([3, 2, 2, 1])
        col1.markdown(f"**{user['username']}**  \n{user.get('email') or '—'}")
        col2.markdown(f"Rôle actuel : `{user['role']}`")

        new_role = col3.selectbox(
            "Nouveau rôle",
            ["user", "admin"],
            index=0 if user["role"] == "user" else 1,
            key=f"role_{user['id']}",
        )
        if new_role != user["role"]:
            if col3.button("Appliquer", key=f"apply_{user['id']}"):
                r = api("PATCH", f"/admin/users/{user['id']}/role", json={"role": new_role})
                if r and r.status_code == 200:
                    st.success(f"Rôle de {user['username']} mis à jour.")
                    st.rerun()

        if user["username"] != st.session_state.username:
            if col4.button("🗑️", key=f"del_{user['id']}"):
                r = api("DELETE", f"/admin/users/{user['id']}")
                if r and r.status_code == 204:
                    st.success(f"Utilisateur {user['username']} supprimé.")
                    st.rerun()


# ── Main app ──────────────────────────────────────────────────────────────────
def main_app():
    sidebar()

    if st.session_state.role == "admin":
        tab_chat, tab_my_history, tab_all_history, tab_users = st.tabs([
            "💬 Assistant", "📋 Mon historique", "📊 Tout l'historique", "👥 Utilisateurs"
        ])
        with tab_chat:
            chat_tab()
        with tab_my_history:
            my_history_tab()
        with tab_all_history:
            all_history_tab()
        with tab_users:
            user_management_tab()
    else:
        tab_chat, tab_history = st.tabs(["💬 Assistant", "📋 Mon historique"])
        with tab_chat:
            chat_tab()
        with tab_history:
            my_history_tab()


# ── Entry point ───────────────────────────────────────────────────────────────
if st.session_state.token:
    main_app()
else:
    auth_page()
