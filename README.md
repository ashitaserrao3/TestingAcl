# Dummy_website – ACL Dummy

Just a dummy acl website to test and track the updates and push new changes/requirements in original repo.

A Streamlit login page: sign in with a username and password and the app shows
"Yes, you did it!".

## Deploy (Streamlit Community Cloud)
1. Push this repo to GitHub.
2. App → Settings → **Secrets** → paste the contents of your private `secrets.toml`
   (layout: see `secrets.toml.example`). Logins are **not** stored in the repo.
3. New/changed password: `python generate_password.py`, paste the hash into Secrets.

Local run: copy your secrets to `.streamlit/secrets.toml` (git-ignored), then `streamlit run app.py`.
