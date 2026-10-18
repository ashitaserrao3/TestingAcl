# Dummy_website – ACL Dummy

Just a dummy acl website to test and track the updates and push new changes/requirements in original repo.

A Streamlit **Flight Schedule**: pick Origin and Destination to see the route, weekly
flights, flight count, status, and every flight with its product, ETD and
**CPKG (₹/kg) at 45+ and 100+ kg**. Hover a CPKG value to see its breakdown
(tariff + surcharge + add-on). The lowest CPKG on the route is shown in light red.

* Everyone must sign in. Everyone who signs in sees the Flight Schedule.
* Only the `ashita` account gets the sidebar with the two uploads:
  * **Upload schedule** – the DGCA approved-schedule PDFs (one per airline) give the
    flights; reading them takes a few minutes. The ATC/AOC schedule workbook (.xlsx)
    gives station names, Add-on Rates and Network Surcharges.
  * **Upload tariff rates** – the airline tariff files (.xlsx): IndiGo, Air India,
    Akasa, SpiceJet, Star Air. Keep the airline's file name; the effective date is
    read from it.
* Uploaded files are saved on the app's server, not in GitHub. On Streamlit Cloud
  they last until the app restarts; after a restart, upload them again.

The rate and schedule engine (`tariffapp/`) is copied from the TarrifApp repo.

## Deploy (Streamlit Community Cloud)
1. Push this repo to GitHub.
2. App → Settings → **Secrets** → paste the contents of your private `secrets.toml`
   (layout: see `secrets.toml.example`). Logins are **not** stored in the repo.
3. New/changed password: `python generate_password.py`, paste the hash into Secrets.

Local run: copy your secrets to `.streamlit/secrets.toml` (git-ignored), then `streamlit run app.py`.

## Tests
```
pip install -r requirements.txt pytest
python -m pytest tests
```
