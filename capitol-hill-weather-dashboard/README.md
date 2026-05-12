# Capitol Hill Infant Weather Dashboard

Static dashboard for deciding whether to take an infant outside on Capitol Hill, DC.

## Run Locally

```sh
python3 -m http.server 5173
```

Open `http://127.0.0.1:5173`.

## Test

```sh
node --test tests/*.test.js
python3 scripts/daily_email.py --dry-run
```

## Publish With GitHub Pages

1. Push this repository to GitHub.
2. In GitHub, go to **Settings -> Pages**.
3. Set **Build and deployment** to **GitHub Actions**.
4. Run the `Deploy weather dashboard` workflow, or push to `main`.

The workflow publishes the contents of `capitol-hill-weather-dashboard`.

## Daily Email

The `Daily weather email` workflow runs hourly. The script sends only when local Capitol Hill time matches `DAILY_EMAIL_HOUR`, so daylight saving time is handled without editing the cron schedule.

Add these repository secrets in **Settings -> Secrets and variables -> Actions**:

- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `MAIL_FROM`
- `MAIL_TO`

`MAIL_TO` can contain both recipients, separated by commas.

For Gmail, use an app password rather than your normal Google password.

Optional repository variable:

- `DASHBOARD_URL`: the GitHub Pages URL, included as a link in the email.
- `DAILY_EMAIL_HOUR`: hour in 24-hour Capitol Hill time, default `9`.
