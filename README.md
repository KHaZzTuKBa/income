# Portfel

Личный учёт брокерского счёта Т‑Инвестиций. FastAPI + React + PostgreSQL в Docker, вход одним пользователем.

## Быстрый старт

Нужен [Docker Desktop](https://www.docker.com/products/docker-desktop/).

```bash
copy .env.example .env
```

В `.env` задайте `APP_PASSWORD`, `SESSION_SECRET` и `FERNET_KEY` (ключи можно сгенерировать командой из комментария в `.env.example`).

```bash
docker compose up --build
```

- UI: http://localhost:8080
- OpenAPI: http://localhost:8000/api/docs

Войдите логином и паролем из `.env` (`APP_USERNAME` / `APP_PASSWORD`).

Остановка: `docker compose down`. Данные Postgres остаются в volume `postgres_data`.

## Локальная разработка без контейнеров api/web

Postgres всё равно в Docker:

```bash
docker compose up db -d
```

Бэкенд (из `backend/`, Python 3.12):

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

Фронт (из `frontend/`, Node 22):

```bash
npm ci
npm run dev
```

Vite на http://localhost:5173 проксирует `/api` на бэкенд.

## Тесты и линт

```bash
docker compose exec api pytest
```

Локально в `backend/`: `ruff check .` и `pytest`.

## CI/CD

Пуш в `main` собирает образы, публикует их в GHCR и (если заданы секреты) обновляет контейнеры на VDS. Pull request гоняет проверки, образы не публикует.

Образы:

- `ghcr.io/<owner>/portfel-api`
- `ghcr.io/<owner>/portfel-worker` (тот же Dockerfile, что api)
- `ghcr.io/<owner>/portfel-web`

Теги: `<git sha>` и `latest`. Реестр: `GITHUB_TOKEN`, отдельно PAT для GHCR не нужен.

### Секреты репозитория (Settings → Secrets and variables → Actions)

| Секрет | Зачем |
| --- | --- |
| `VDS_HOST` | IP или DNS сервера |
| `VDS_USER` | SSH-пользователь |
| `VDS_SSH_KEY` | Приватный ключ целиком (`BEGIN … PRIVATE KEY`) |
| `VDS_APP_DIR` | Необязательно. Каталог на сервере, по умолчанию `/opt/portfel` |

Публичный ключ должен быть в `~/.ssh/authorized_keys` у `VDS_USER`. Пока три обязательных секрета пустые, job деплоя пропускается, образы всё равно попадают в GHCR.

В репозитории: Settings → Actions → General → Workflow permissions → Read and write. Для организации: пакеты GHCR должны быть доступны Actions.

### Что лежит на VDS

Прокси, DNS, сертификаты и файрвол не настраиваем — это на вашей стороне. Нужны Docker с плагином Compose v2 и два файла в `/opt/portfel` (или в `VDS_APP_DIR`):

1. `docker-compose.prod.yml` — копия из репозитория
2. `.env` по образцу `.env.example`

В `.env` на сервере обязательно:

- свои `APP_PASSWORD`, `SESSION_SECRET`, `FERNET_KEY`, `POSTGRES_PASSWORD`
- `GHCR_OWNER` — GitHub-логин или орг **строчными** буквами
- при HTTPS: `COOKIE_SECURE=true`

Полный git-клон на сервере не нужен. Миграции `alembic upgrade head` выполняются при старте контейнера `api`.

Ручной pull на сервере для приватного GHCR не сработает без `docker login ghcr.io`. Pipeline логинится сам на время деплоя через `GITHUB_TOKEN`.
