# Portfel

Личный учёт брокерского счёта Т‑Инвестиций. FastAPI + React + PostgreSQL в Docker, вход одним пользователем.

Для агентов и нового контекста чата: **[AGENTS.md](AGENTS.md)** — архитектура, карта файлов, метрики, как тестировать и что не ломать.

## Быстрый старт

Нужен [Docker Desktop](https://www.docker.com/products/docker-desktop/).

```bash
copy .env.example .env
```

В `.env` задайте `APP_PASSWORD`, `SESSION_SECRET` и `FERNET_KEY` (ключи можно сгенерировать командой из комментария в `.env.example`).

```bash
docker compose up --build
```

- UI: http://localhost:8180
- OpenAPI: http://localhost:8180/api/docs (через nginx) или напрямую http://localhost:8100/api/docs

Порты на хосте не пересекаются с типичными 8000/8080 других проектов. Если всё же заняты, задайте в `.env` `PORTFEL_WEB_PORT`, `PORTFEL_API_PORT`, `PORTFEL_DB_PORT`.

Логин и пароль из `.env` (`APP_USERNAME` / `APP_PASSWORD`) — это администратор: он одобряет заявки на регистрацию и управляет аккаунтами, своего портфеля у него нет. Чтобы вести портфель, зарегистрируйтесь на `/register` и одобрите заявку под админом.

Дальше: Настройки → вставьте read-only токен Invest API → «Сохранить токен» → «Обновить». Токен проверяется через GetAccounts, шифруется Fernet и в UI не возвращается. Синк по расписанию — в 08:00 и 20:00 по Москве.

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
uvicorn app.main:app --reload --port 8100
```

Фронт (из `frontend/`, Node 22):

```bash
npm ci
npm run dev
```

Vite на http://localhost:5173 проксирует `/api` на бэкенд `localhost:8100`. Если контейнер api из compose запущен, локальный uvicorn на 8100 не поднимется — остановите его (`docker compose stop api worker`).

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
