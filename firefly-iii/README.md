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
4. Copy token and add as `IMPORTER_ACCESS_TOKEN` in Portainer stack env

### 3. Configure SimpleFIN (US Bank Sync)

1. Go to https://beta-bridge.simplefin.org/
2. Create account and link banks (~$1.50/month)
3. Get access token
4. Add as `SIMPLEFIN_TOKEN` in Portainer stack env
5. Restart firefly-importer container

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
