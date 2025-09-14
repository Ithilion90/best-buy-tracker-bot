# Deploy on AWS

This guide shows two proven options to run the Telegram bot on AWS.

- Option A (simple): EC2 VM + systemd + SQLite (or RDS Postgres)
- Option B (scalable): ECS Fargate (container) + RDS Postgres

Both require a Telegram bot token and optional Keepa API key.

## Prerequisites

- Telegram bot token from @BotFather (BOT_TOKEN)
- Optional Keepa key (KEEPA_API_KEY)
- Affiliate tag (AFFILIATE_TAG)
- Choose storage:
  - SQLite (default): simple, single instance only
  - Postgres (recommended for prod/HA): set DATABASE_URL

Environment variables read by the app (see `src/config.py`):
- BOT_TOKEN (required)
- AFFILIATE_TAG (optional, default bestbuytracker-21)
- KEEPA_API_KEY (optional)
- KEEPA_DOMAIN (optional, default it)
- CHECK_INTERVAL_MINUTES (default 30)
- DATABASE_PATH (default tracker.db when SQLite)
- DATABASE_URL (Postgres uri, enables PG automatically)
- DB_POOL_SIZE (default 5)
- USER_AGENT (optional)

---

## Option A: EC2 + systemd

Good for a single small instance. Start with SQLite, or use RDS Postgres.

1) Create EC2 instance
- Choose Amazon Linux 2023 or Ubuntu 22.04, t3.micro or t3.small
- Open outbound internet (to reach Telegram/Keepa/Amazon); no inbound ports needed

2) Install dependencies
- Python 3.11, Git (or copy files via ZIP/SCP)
- Create a dedicated user `bot`

3) Deploy code
- Copy repo contents to `/opt/best-buy-tracker` (or clone)
- Create `.env` with your secrets (owned by `bot`, permission 600)
  - BOT_TOKEN=...
  - AFFILIATE_TAG=...
  - KEEPA_API_KEY=...
  - Optional: DATABASE_URL=postgres://user:pass@host:5432/dbname

4) Run as a service (systemd)
- Create `/etc/systemd/system/best-buy-tracker.service`:

  [Unit]
  Description=Best Buy Tracker Bot
  After=network-online.target
  Wants=network-online.target

  [Service]
  Type=simple
  User=bot
  WorkingDirectory=/opt/best-buy-tracker
  Environment=PYTHONUNBUFFERED=1
  ExecStart=/usr/bin/python3 -m src.bot
  Restart=always
  RestartSec=5

  [Install]
  WantedBy=multi-user.target

- sudo systemctl daemon-reload
- sudo systemctl enable --now best-buy-tracker
- Check logs: `journalctl -u best-buy-tracker -f`

5) Database
- SQLite: file `tracker.db` will be created in working directory
- Postgres: create an RDS PostgreSQL instance and set DATABASE_URL, then restart the service

6) Backups & updates
- SQLite: snapshot the instance volume or back up `tracker.db`
- Postgres: use RDS automated backups
- For updates: pull new code and `sudo systemctl restart best-buy-tracker`

---

## Option B: ECS Fargate + RDS Postgres

Recommended for reliability, rolling updates, and no servers to manage.

1) Build and push the image
- From the project root with Docker installed:
  - docker build -t best-buy-tracker:latest .
  - Create an ECR repo, then tag and push (replace AWS account/region):
    - aws ecr get-login-password --region eu-west-1 | docker login --username AWS --password-stdin <acc>.dkr.ecr.eu-west-1.amazonaws.com
    - docker tag best-buy-tracker:latest <acc>.dkr.ecr.eu-west-1.amazonaws.com/best-buy-tracker:latest
    - docker push <acc>.dkr.ecr.eu-west-1.amazonaws.com/best-buy-tracker:latest

2) Provision RDS Postgres
- Create a small Postgres instance (db.t4g.micro)
- Security group allows inbound from ECS tasks SG on 5432
- Get the connection string (DATABASE_URL) and store it securely

3) Secrets and config
- Put BOT_TOKEN, KEEPA_API_KEY, AFFILIATE_TAG, DATABASE_URL into AWS Secrets Manager or SSM Parameter Store
- In the ECS task definition, map secrets to env vars

4) Create ECS service (Fargate)
- Cluster (Fargate), task with 0.25 vCPU / 512MB RAM is enough to start
- Container image: ECR URI
- Command: default `python -m src.bot`
- Env: CHECK_INTERVAL_MINUTES=30 (or your choice), KEEPA_DOMAIN=it
- Networking: public subnet + NAT or private subnets with NAT Gateway; outbound internet is required
- No load balancer needed (Telegram uses outbound polling). Optionally attach a dummy health check command.

5) Logs and monitoring
- Enable AWS CloudWatch Logs in the task definition
- The app logs INFO to stdout; use CW Logs to inspect

6) Rollouts
- Push a new image tag and update the ECS service to roll out

---

## Using SQLite in containers?

Not recommended for ECS (ephemeral storage). Prefer RDS. For EC2 single instance, SQLite is fine.

---

## Troubleshooting

- Bot doesn’t start: ensure BOT_TOKEN is set; `Config.validate_config()` requires a colon in the token format
- No DB: if DATABASE_URL provided, ensure `psycopg2-binary` is installed (it is in `requirements.txt`) and security groups allow access
- Timeouts: tweak REQUEST_TIMEOUT_SECONDS or CHECK_INTERVAL_MINUTES via env vars
- Rate limits: Keepa has quotas; consider increasing interval if needed

---

## Security notes

- Never hardcode tokens. Use `.env` on EC2 with proper file perms, or Secrets Manager for ECS
- Rotate tokens/keys periodically
- Limit egress with VPC endpoints or NAT as needed; open only what’s required

---

## Quick reference

- Run locally with Docker:
  docker build -t best-buy-tracker .
  docker run --rm -e BOT_TOKEN=xxx -e AFFILIATE_TAG=yyy -e KEEPA_API_KEY=zzz best-buy-tracker

- Override DB in Docker:
  docker run --rm -e BOT_TOKEN=xxx -e DATABASE_URL=postgres://user:pass@host:5432/db best-buy-tracker