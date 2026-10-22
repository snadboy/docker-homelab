# Firefly III

Personal finance manager with bank sync via SimpleFIN.

## URLs

- **Main App**: https://firefly.isnadboy.com
- **Data Importer**: https://firefly-import.isnadboy.com

## Pre-Deployment

### Create Volumes

```bash
docker volume create firefly-upload
docker volume create firefly-db
docker volume create firefly-importer-configs
docker volume create firefly-passport
```

`firefly-passport` holds Firefly's OAuth signing keys (`oauth-private.key`,
`oauth-public.key`, owned by uid 33, mode 600). Without it the keys are regenerated on
every container recreate and **every personal access token stops working** — that is
what silently broke the importer in 2026. Seed it from a running container:

```bash
for f in oauth-private.key oauth-public.key; do
  docker cp firefly-iii:/var/www/html/storage/$f - | docker run --rm -i -v firefly-passport:/k alpine tar -x -C /k
done
docker run --rm -v firefly-passport:/k alpine sh -c 'chown -R 33:33 /k && chmod 700 /k && chmod 600 /k/*'
```

### Generate Secrets

```bash
# APP_KEY (32 characters)
head /dev/urandom | LC_ALL=C tr -dc 'A-Za-z0-9' | head -c 32 && echo

# DB_PASSWORD
head /dev/urandom | LC_ALL=C tr -dc 'A-Za-z0-9' | head -c 24 && echo

# STATIC_CRON_TOKEN
head /dev/urandom | LC_ALL=C tr -dc 'A-Za-z0-9' | head -c 32 && echo

# AUTO_IMPORT_SECRET
head /dev/urandom | LC_ALL=C tr -dc 'A-Za-z0-9' | head -c 32 && echo
```

## Post-Deployment Setup

### 1. Create Admin Account

Navigate to https://firefly.isnadboy.com and register. First user becomes admin.

### 2. Generate Importer Access Token

1. Login to Firefly III
2. Go to **Profile** -> **OAuth** -> **Personal Access Tokens**
3. Create new token (description: "Data Importer")
4. Copy token and add as `IMPORTER_ACCESS_TOKEN` in `.env`, then `docker compose up -d firefly-importer`

### 3. Configure SimpleFIN (US Bank Sync)

1. Go to https://beta-bridge.simplefin.org/
2. Create account and link banks (~$1.50/month)
3. Get access token
4. Add as `SIMPLEFIN_TOKEN` in `.env`
5. Restart firefly-importer container

### 4. Nightly auto-import

`firefly-cron` runs `firefly-cron.sh` (container TZ is UTC):

| UTC | Job |
|---|---|
| 05:00 | `cron` — Firefly's `/api/v1/cron/$STATIC_CRON_TOKEN` (recurring transactions, bills) |
| 06:00 | `import` — `/autoimport` over every config JSON in the `firefly-importer-configs` volume |

Each run logs one line (`docker logs firefly-cron`). To give the import something to do,
run one SimpleFIN import by hand in the importer UI, download its configuration JSON at
the end, and copy it into the volume:

```bash
docker cp simplefin.json firefly-importer:/var/www/html/storage/configurations/
```

The JSON contains the SimpleFIN access URL, so treat it as a secret. Set `KUMA_PUSH_URL`
in `.env` to an Uptime Kuma push monitor's URL to get a heartbeat after each successful
import. Test a job by hand with `docker exec firefly-cron sh /firefly-cron.sh import`.

## Backup

```bash
# Database dump
docker exec firefly-db pg_dump -U firefly firefly > firefly_backup_$(date +%Y%m%d).sql

# Restore
cat firefly_backup.sql | docker exec -i firefly-db psql -U firefly -d firefly
```

## Troubleshooting

```bash
# View logs
docker logs firefly-iii
docker logs firefly-db

# Test database connection
docker exec -it firefly-db psql -U firefly -d firefly -c "SELECT 1"

# Reset admin password
docker exec -it firefly-iii php artisan firefly-iii:change-password --email=your@email.com
```

## Adding AI Categorization (Optional)

Add to docker-compose.yml:

```yaml
  firefly-ai-categorize:
    image: ghcr.io/bahuma20/firefly-iii-ai-categorize:latest
    container_name: firefly-ai-categorize
    restart: unless-stopped
    depends_on:
      - firefly-iii
    labels:
      - "snadboy.revp.3000.domain=firefly-ai.isnadboy.com"
    ports:
      - "5012:3000"
    environment:
      - FIREFLY_URL=http://firefly-iii:8080
      - FIREFLY_PERSONAL_TOKEN=${IMPORTER_ACCESS_TOKEN}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - FIREFLY_TAG=AI categorized
      - ENABLE_UI=true
    networks:
      - firefly-internal
```

Add to .env:
```bash
OPENAI_API_KEY=sk-...
```

Then configure webhook in Firefly III:
1. **Automation** -> **Webhooks** -> **Create Webhook**
2. Title: "AI Categorizer"
3. Trigger: "After transaction creation"
4. Response: "Transaction details"
5. URL: `http://firefly-ai-categorize:3000/webhook`
