# Pulse Price Compare

Pulse Price Compare is a Python web application for comparing product prices across online sources. Search for any product, collect live shopping results from configured APIs, rank the cheapest offers, highlight the highest savings, compare listings from multiple platforms in one browser view, and save searched products in MySQL.

## What It Does

- Search a product from a web page
- Pull offers from live shopping APIs when credentials are configured
- Fall back to demo marketplace data so the project still runs without paid keys
- Rank results by lowest price
- Highlight the biggest savings using original vs current price
- Show comparison cards and a platform comparison table
- Save every completed product search in a MySQL `searched_products` table

## Provider Support

- `demo`
  Uses the bundled sample catalog in `data/demo_products.json`
- `serpapi`
  Uses SerpApi Google Shopping as the primary live search source and expands product results into merchant store offers when available
- `dataforseo`
  Uses the Google Shopping merchant endpoints from DataForSEO

You can enable one or more providers with `DATA_PROVIDERS`.

## Setup

1. Install dependencies:

   ```bash
   python -m pip install -r requirements.txt
   ```

2. Copy environment settings:

   ```bash
   copy .env.example .env
   ```

3. Choose providers in `.env`:

   ```env
   DATA_PROVIDERS=serpapi,demo
   SERPAPI_KEY=your_key_here
   DATAFORSEO_LOGIN=your_login_here
   DATAFORSEO_PASSWORD=your_password_here
   ```

   If you do not add a SerpApi key, the app falls back to demo mode.

4. Start MySQL from XAMPP, then keep the default MySQL settings or adjust them in `.env`:

   ```env
   MYSQL_ENABLED=true
   MYSQL_HOST=127.0.0.1
   MYSQL_PORT=3306
   MYSQL_USER=root
   MYSQL_PASSWORD=
   MYSQL_DATABASE=pulse_price_compare
   ```

   The app automatically creates the `pulse_price_compare` database and `searched_products` table on startup. You can also import `database.sql` manually through phpMyAdmin.
   
Then open:

`http://127.0.0.1:5000`

## VS Code Setup

- Open the project folder in VS Code
- Accept the recommended Python extensions when prompted
- Use `Run and Debug` and choose `Run Pulse Price Compare`
- Or use `Terminal > Run Task` and pick:
  - `Install Requirements`
  - `Run App`
  - `Run Tests`

The workspace is already configured for the `src/` layout, pytest discovery, and the bundled Python runtime.

## Submission Notes

- Do not submit the raw project folder as a zip because it may include local-only directories such as `.venv/`, `.tmp/`, `__pycache__/`, and test artifacts.
- Create the submission zip from the tracked project files, for example with `git archive`, so ignored runtime data such as `data/search_history_backup.json` and `data/search_history_pending.json` stay out of the archive.
- `tests/conftest.py` already adds `src/` to `sys.path`, so `pytest` runs from the project root without `pip install -e .`.
- `database.sql` matches the MySQL schema created in `src/pricepulse_compare/database.py` for the `searched_products` table.

## API Endpoints

- `GET /`
  Web interface
- `GET /api/search?q=iphone+15`
  JSON search response
- `GET /search-history`
  Browser page for saved searched products
- `GET /api/search-history`
  JSON response for saved searched products
- `GET /health`
  Health check, including MySQL search-history status

## Project Structure

```text
.
|-- app.py
|-- database.sql
|-- data/
|   `-- demo_products.json
|-- static/
|   |-- app.js
|   `-- styles.css
|-- templates/
|   `-- index.html
`-- src/
    `-- pricepulse_compare/
        |-- __init__.py
        |-- models.py
        |-- settings.py
        `-- services/
            |-- search_service.py
            `-- providers/
                |-- base.py
                |-- dataforseo_provider.py
                |-- demo_provider.py
                `-- serpapi_provider.py
```

## Notes

- SerpApi Google Shopping is the primary live provider and the app also requests immersive product store offers so links can point to merchant pages instead of only Google product pages when SerpApi returns store data.
- DataForSEO Google Shopping uses task-based merchant endpoints, so the app posts a task and polls briefly for the result.
- Demo data is included so the site can still be shown in class or in a viva without external API keys.
