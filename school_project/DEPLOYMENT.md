# Deployment Checklist — Mater Domini Schools Website

This is a practical, in-order checklist for taking the public website and
the IT Staff results dashboard from development to production. Work
through it top to bottom the first time you deploy; keep it handy for
future redeploys too.

## Recommended timeline for your launch

Given you're aiming for roughly two weeks out, here's the order that
minimizes risk:

1. **Days 1–3: Choose hosting, provision Postgres, point the domain** (steps 1–3 below). Domain DNS propagation can take hours, so start this immediately even if nothing else is ready.
2. **Days 3–5: Deploy the code with demo/seed data still in place**, run through the full verification checklist (step 8) against that demo data first. It's much easier to spot a bug in a placeholder result than to debug live while parents are watching.
3. **Days 5–10: Import real data** (step 7b) — one class/arm workbook at a time, checking each prints correctly before moving to the next. This is naturally the slowest step; budget the most time here.
4. **Days 10–12: Create IT staff accounts**, test dashboard access and print a small set of real results before wider use.
5. **Days 12–14: Final full verification pass, then publish results and announce the site.** Keep the old system available in parallel for a few days as a fallback in case something unexpected comes up.

## 1. Choose where it will run

Any of these work with zero code changes, since settings are already
environment-driven (`config/settings/prod.py`):

- A VPS you manage yourself (DigitalOcean, Linode, a Nigerian host) running Gunicorn behind Nginx
- A PaaS (Railway, Render, PythonAnywhere) that handles the server for you

If you're unsure, a PaaS is the least maintenance for a small school site.

## 2. Get a Postgres database

Production uses PostgreSQL, not the SQLite file you've been developing
with (SQLite is fine for one developer on one laptop; it is not safe for
a live site with concurrent users). Most hosts above offer a Postgres
add-on. You'll get a `DATABASE_URL` connection string from whichever
host you choose — keep it, you need it in step 4.

## 2b. Check whether your host's file storage is actually permanent

**This matters a lot for you specifically**, since you'll have real
uploaded content: student passport photos, staff photos, gallery photos,
and the result workbooks you import. Django stores these as ordinary
files on disk (`MEDIA_ROOT`), which works perfectly — **as long as that
disk survives a redeploy.**

Some free/cheap PaaS tiers (Render's free web services, for example) use
an *ephemeral* filesystem: every time you redeploy or the service
restarts, anything written to disk is wiped, including `media/`. Your
database records would survive, but every uploaded photo would 404.

Before launch, confirm one of these is true for your host:
- You're on a paid tier with a persistent disk/volume attached, with
  `MEDIA_ROOT` pointed at that volume, **or**
- You're using a traditional VPS (Option B below), where the disk is
  simply always there, **or**
- You've added object storage (e.g. an S3-compatible bucket via
  `django-storages`) — a reasonable next step if you outgrow local
  storage, but not something this project sets up by default (kept out
  to avoid an unnecessary dependency until you actually need it).

If in doubt, ask your host directly: "does my app's local disk persist
across deploys and restarts?" Get a clear yes before you rely on it for
real student data.

## 3. Buy/point the domain

Point `materdominischool.com.ng` (and `www.` if you use it) at your
server or hosting platform's IP/CNAME, per your host's instructions.
This can take a few hours to propagate — do it early.

## 4. Set environment variables

None of these live in code — set them on your server or hosting
platform's dashboard:

| Variable | Value |
|---|---|
| `DJANGO_SETTINGS_MODULE` | `config.settings.prod` |
| `DJANGO_SECRET_KEY` | A long random string — **generate a fresh one**, don't reuse the dev one. Run: `python -c "import secrets; print(secrets.token_urlsafe(50))"` |
| `DJANGO_DEBUG` | `False` (or leave unset — False is the default) |
| `DJANGO_ALLOWED_HOSTS` | `materdominischool.com.ng,www.materdominischool.com.ng` |
| `DATABASE_URL` | The Postgres connection string from step 2 |

`.env.example` in the repo shows this same list — copy it as a starting
point, never commit the real filled-in version.

## 5. Install dependencies and run migrations

```bash
pip install -r requirements/prod.txt
python manage.py migrate
python manage.py createsuperuser
```

The results migration creates the `IT Staff` group and grants it only the
student-results dashboard permission. It does not change or delete student,
class, term, session, or result records. No new Render environment variables
are required.

On Render, run `python manage.py migrate --noinput` from the service Shell
before releasing the new code, or configure it as the service's pre-deploy
command if that feature is available on your plan. The existing `build.sh`
continues to install dependencies and run `collectstatic`; no database
connection or storage settings need to change.

Then load starter content (real school info + placeholder demo entries
you'll replace via `/admin/`):

```bash
python manage.py seed_demo_data
```

## 6. Collect static files

**This step is easy to forget and the site will look broken without it**
(unstyled HTML, no logo) — WhiteNoise requires a build manifest that only
`collectstatic` generates:

```bash
python manage.py collectstatic --noinput
```

Re-run this every time you deploy new CSS/JS/image changes.

**Same requirement applies to running the automated tests.** Django's test
runner always forces `DEBUG=False` internally, regardless of your settings
file — so `python manage.py test` hits the exact same "no static manifest"
error described above if `collectstatic` hasn't been run at least once.
Run `python manage.py collectstatic --noinput` before `python manage.py test`
in any fresh environment (a new dev machine, CI, etc.).

## 7. Run with Gunicorn (if self-hosting, not using a PaaS)

```bash
gunicorn config.wsgi:application --bind 0.0.0.0:8000
```

Put Nginx in front of it as a reverse proxy + HTTPS terminator. A
minimal Nginx config:

```nginx
server {
    listen 80;
    server_name materdominischool.com.ng www.materdominischool.com.ng;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name materdominischool.com.ng www.materdominischool.com.ng;

    ssl_certificate     /etc/letsencrypt/live/materdominischool.com.ng/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/materdominischool.com.ng/privkey.pem;

    location /static/ {
        alias /path/to/school_project/staticfiles/;
    }
    location /media/ {
        alias /path/to/school_project/media/;
    }
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Use [Certbot](https://certbot.eff.org/) for a free Let's Encrypt
certificate. `SECURE_SSL_REDIRECT` and friends are already turned on in
`prod.py`, so once HTTPS is live, HTTP will auto-redirect.

## 7b. Import and verify results before launch

You're rebuilding real result data for JSS1–SS3 (all arms) for the
current session. Do this **on the production database, after deploying
but before announcing the site**, in this order:

1. Log into `/admin/` with the real superuser account (not the demo one).
2. For each class/arm workbook, use `/staff/upload-workbook/` — this creates
   every student in the REGISTER sheet automatically, then writes
   whatever term sheets are present. Repeat once per class/arm.
3. After all classes are in, run `python manage.py recalculate_positions`
   once to make sure every class's rankings reflect the complete data
   (the upload does this per-upload already, but one final pass after
   *all* classes exist is a good sanity check).
4. In Django Admin, create each IT account and assign it to the `IT Staff`
  group. Do not mark the account as staff or superuser; the dashboard
  permission is sufficient and does not grant Django Admin access.
5. Sign in at `/staff/login/`, select class, session and term in
  `/staff/dashboard/`, and verify individual and class print previews.

The public scratch-card workflow is retired. `/check-result/` is no longer
a valid route. IT staff use the dashboard; the superuser retains full
Django Admin access.

**Do not run `seed_demo_data` or `seed_results_demo_data` on the
production database.** Those are for local development only — they
create fictional students, sample news, and placeholder staff entries
that have no business on the live site. On production, only ever run
`migrate` and then enter real data through the admin/workbook uploads.

## 8. Verify before telling anyone the site is live

- [ ] Visit every page: `/`, `/about/`, `/academics/`, `/admissions/`, `/staff/`, `/management/`, `/gallery/`, `/news/`, `/events/`, `/contact/`
- [ ] Submit the Admissions inquiry form and the Contact form — confirm both save (check `/admin/`)
- [ ] Log into `/admin/` and replace every `[Placeholder ...]` entry (staff bios, sample news/events) with real content — search the admin for `[Placeholder` and `[Sample` to find every one
- [ ] Upload the school's real photos in Gallery, staff photos in Staff Directory
- [ ] Confirm `/check-result/` is retired and the public site links to `/staff/login/`, not Django Admin
- [ ] Sign in with an IT account, confirm dashboard access, student search and filters, and print an individual result
- [ ] Print a class batch and confirm each student's sheet starts on a new page; printer margins can differ from browser preview
- [ ] Confirm an IT account cannot access `/admin/`, while the superuser can
- [ ] Confirm HTTPS works and HTTP redirects to it
- [ ] Confirm `/admin/` requires login and isn't publicly browsable
- [ ] Check the site on an actual phone, not just a resized browser window
- [ ] Visit a nonsense URL (e.g. `/asdf/`) and confirm the custom "Page Not Found" page shows, not a raw Django error
- [ ] Check `/sitemap.xml` and `/robots.txt` both load and list the real domain (not `127.0.0.1`)
- [ ] Run `python manage.py check --deploy` against your production settings — it should report zero issues; if anything shows up, fix it before announcing the site is live
- [ ] Confirm no `[Demo ...]`/fictional student data from `seed_results_demo_data` exists on production — that command should never have been run there

## 9. Ongoing maintenance

- **Backups**: set up automatic daily Postgres backups through your host — this is more important than almost anything else on this list. Losing the database means losing every result, staff profile, and news post.
- **Updating content**: authorized administrators manage site content and imports via `/admin/`; IT accounts use `/staff/dashboard/` for student result retrieval and printing.
- **Deploying code changes**: pull the latest code, `pip install -r requirements/prod.txt` (in case dependencies changed), `python manage.py migrate` (in case models changed), `python manage.py collectstatic --noinput`, restart Gunicorn.
- **Rotating the SECRET_KEY**: only if you suspect it's been exposed — rotating it invalidates all active sessions (everyone gets logged out) but not stored data.
