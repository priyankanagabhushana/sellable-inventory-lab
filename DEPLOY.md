# Deploy Sellable to Streamlit Community Cloud

Repo is already public:
https://github.com/priyankanagabhushana/sellable-inventory-lab

## Steps (≈2 minutes)

1. Open https://share.streamlit.io/ and sign in with the **priyankanagabhushana** GitHub account.
2. Click **Create app** / **New app**.
3. Settings:
   - Repository: `priyankanagabhushana/sellable-inventory-lab`
   - Branch: `main`
   - Main file path: `app.py`
4. Deploy. The default experience uses a stable offline schedule and does not need secrets.
5. Add the verified `*.streamlit.app` URL to the README.

Do not enable `SELLABLE_ENABLE_PUBLIC_SCHEDULE_REFRESH` in the hosted app until
the source terms for the optional programme-listings adapter have been reviewed.

## Optional: record the 90s demo

Follow [docs/DEMO_STORYBOARD.md](docs/DEMO_STORYBOARD.md).
Use the screenshots in `docs/` as frames if you prefer a Loom over a local recording.

## Local run

```bash
cd sellable-inventory-lab
source .venv/bin/activate
streamlit run app.py
```
