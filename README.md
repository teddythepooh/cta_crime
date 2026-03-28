# Chicago Transit Crimes Dashboard

This is a simple dashboard to visualize crimes in Chicago's rapid transit system. covering over 200 miles of track across Chicagoland.

## Requirements
1. Python >= 3.8 (minumum version for `uv`, a Python package manager)
2. Socrata API

## Instructions (Local Deployment)
1. Generate API key and app token for Socrata API through https://evergreen.data.socrata.com/. See Developer Settings after creating an account. Set your API Key ID, API Key Secret, and App Token in `./streamlist/secrets.toml` as `socrata_username`, `socrata_password`, and `socrata_app_token`, respectively.
2. Do `pip install uv` (if needed), then `uv sync` from this project's root directory.
3. Do `uv run streamlit run ./app.py`.
