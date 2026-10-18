import copy

import streamlit as st
import streamlit_authenticator as stauth

st.set_page_config(page_title="ACL Login", page_icon="✈️", layout="centered")

# =====================================================
# AUTHENTICATION
# Users + cookie key live in Streamlit Secrets, never in the repo.
#   Community Cloud : App settings -> Secrets
#   Local run       : .streamlit/secrets.toml (git-ignored)
# =====================================================


def _to_dict(obj):
    """st.secrets is read-only; the authenticator needs a normal dict."""
    if hasattr(obj, "items"):
        return {k: _to_dict(v) for k, v in obj.items()}
    return copy.deepcopy(obj)


if "credentials" not in st.secrets or "cookie" not in st.secrets:
    st.error(
        "Login settings are missing. Add the [credentials] and [cookie] sections "
        "to Streamlit Secrets (see secrets.toml.example)."
    )
    st.stop()

credentials = _to_dict(st.secrets["credentials"])
cookie = _to_dict(st.secrets["cookie"])

authenticator = stauth.Authenticate(
    credentials,
    cookie["name"],
    cookie["key"],
    float(cookie.get("expiry_days", 30)),
    auto_hash=False,  # passwords in secrets are already bcrypt hashes
)

# =====================================================
# LOGIN SCREEN
# =====================================================

if not st.session_state.get("authentication_status"):
    try:
        authenticator.login(
            fields={"Form name": "Sign in", "Username": "Username",
                    "Password": "Password", "Login": "Sign in"},
        )
    except Exception as e:
        st.error(e)
    if st.session_state.get("authentication_status") is False:
        st.error("Username or password is incorrect", icon="🔒")

    if st.session_state.get("authentication_status"):
        st.rerun()  # signed in (or remembered) -> show the success screen
    st.stop()

# =====================================================
# SIGNED IN
# =====================================================

# Only this user gets the sidebar with the upload option; everyone else
# sees just the success screen. The password itself is checked above
# against the hash in Secrets.
ADMIN_USER = "ashita"

if st.session_state.get("username") == ADMIN_USER:
    with st.sidebar:
        st.header("Upload")
        uploads = st.file_uploader("Choose files", accept_multiple_files=True)
else:
    uploads = []

st.title("Yes, you did it! 🎉")
st.write(f"You are signed in as **{st.session_state.get('name')}**.")
for f in uploads or []:
    st.write(f"📄 **{f.name}** – {f.size / 1024:.1f} KB")
authenticator.logout("Sign out")
if not st.session_state.get("authentication_status"):
    st.rerun()  # just signed out -> back to the login screen
