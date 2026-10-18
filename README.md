# Dummy_website – ACL Dummy

Just a dummy acl website to test and track the updates and push new changes/requirements in original repo.

A Streamlit **Flight Schedule**: pick Origin and Destination to see the route, weekly
flights, flight count, status, and every flight with its product, ETD and
**CPKG (₹/kg) at 45+ and 100+ kg**. The lowest CPKG on the route is shown in light red.

**CPKG = the airline's own tariff rate (45+ / 100+) + Terminal & Surcharges** from the
Allcargo rate quotation, for that flight: its own flight-number row, else the route's
`ALL` row. Hover a CPKG value to see its breakdown. On an **Akasa special-rate route**
(marked SPECIAL), the special SSP rate is used for 100+ kg; all special routes are
listed under the table.

* Everyone must sign in. Everyone who signs in sees the Flight Schedule.

## The data
The app reads these files from the `data/` folder:

| Folder | Files |
|---|---|
| `data/schedule/dgca/` | DGCA approved-schedule PDFs, one per airline. `schedule.csv` is the app's saved reading of them; it is re-made automatically when the PDFs change (takes a few minutes). |
| `data/rates/` | Airline tariffs (.xlsx): IndiGo, Air India, Akasa, SpiceJet, Star Air. Keep the airline's file name; the effective date is read from it. |
| `data/allcargo/` | The Allcargo rate quotation (.xlsx) – Terminal & Surcharges. |
| `data/special/` | The Akasa special rates (.pdf). |

**To change the data:** on GitHub open the folder, click *Add file → Upload files*,
drop in the new file, delete the old one, and *Commit changes*. Streamlit Cloud
redeploys the app in about a minute with the new data.

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
