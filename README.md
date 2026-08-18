# Containerized URL Shortener Platform

A high-performance, containerized URL shortening microservice engineered with Python (FastAPI), Redis for caching, PostgreSQL for persistent storage, and Nginx as a reverse proxy.

---

## 🏛 Architecture

```
[ Client / Browser ]
        │
        ▼ (Port 80)
┌───────────────────────────────────────────────┐
│              Nginx Reverse Proxy              │
└───────────────────────┬───────────────────────┘
                        │ (Internal Bridge Network: 8000)
                        ▼
┌───────────────────────────────────────────────┐
│             FastAPI App (Non-Root)            │
│  - Multi-stage build                          │
│  - Health-checked                             │
└───────────────┬───────────────────────┬───────┘
                │                       │
     (Read/Write Fallback)        (Cache & Real-time Clicks)
                │                       │
                ▼                       ▼
┌───────────────────────┐       ┌───────────────┐
│     PostgreSQL 15     │       │    Redis 7    │
│  (Persistent Volume)  │       │  (RAM Volume) │
│  *Host Isolated*      │       │ *Host Isolated│
└───────────────────────┘       └───────────────┘
```

---

## ✨ Features

- **URL Shortening & Redirection**: Converts long URLs into 6-character alphanumeric tokens with 307 temporary redirects.
- **Sub-millisecond Reads**: Fast caching layer with Redis read-through and cache hydration.
- **Analytics**: Real-time click tracking synchronized between memory and persistent storage.
- **Container Hardening**: Non-root container execution (`uid 1001`), multi-stage Docker build, and pinned minimal base images.
- **Network Isolation**: PostgreSQL and Redis ports are bound strictly to an internal Docker bridge network and never exposed to the host.
- **Automated CI/CD**: Flake8 linting, Pytest unit tests, Trivy vulnerability scanning, and Docker Hub automated multi-tag releases.

---

## 📦 Prerequisites

- Docker Engine (v20.10+)
- Docker Compose (v2.0+)
- curl or Postman

---

## 🚀 Quick Start

### 1. Clone & Configure
```bash
cp .env.example .env
```

### 2. Build and Launch Containers
```bash
docker compose up -d --build
```

### 3. Verify Container Status
```bash
docker compose ps
```

---

## 📡 API Reference

- `GET /health` - System health inspection
- `POST /shorten` - Shorten URL (Payload: `{"url": "https://example.com"}`)
- `GET /{short_code}` - Redirect to destination
- `GET /stats/{short_code}` - View statistics & click count
