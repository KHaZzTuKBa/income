# Portfel — контекст для агентов

Веб‑сервис учёта портфеля **Т‑Инвестиций** (аналог Snowball Income). Несколько пользователей: регистрация с ручным одобрением администратором; у каждого свой изолированный портфель (свой токен, несколько счетов — брокерский + ИИС). Админ из `.env` портфеля не имеет, только админку. Каталог на диске может называться `income`; приложение и Compose‑проект — **`portfel`**.

Ответы пользователю — **на русском**. UI — на русском. Часовой пояс везде **Europe/Moscow**.

Исходный продуктовый план: `plan.md`. Блоки v1 (0–5) **сделаны**. Не предлагай «следующий блок из плана», пока пользователь сам не попросит новую фичу.

---

## Как работать в этом репозитории

- Меняй только то, что нужно для задачи. Не коммить и не пушь, пока пользователь явно не попросит.
- После правок бэкенда/фронта в Docker нужен **`docker compose up --build`**: compose **не монтирует исходники**.
- Критерий «готово» для UI/API: сервис в Docker, проверка через `http://localhost:8180`. Логин/пароль из `.env` (обычно `admin` / `changeme`) — это **админ**: он видит только `/admin/*`, портфельные API отвечают ему 403. Для проверки портфеля нужен обычный одобренный пользователь. Браузерных MCP может не быть — достаточно HTTP + логи.
- На Windows PowerShell **нельзя** `&&`. Пиши `;`. JSON для `curl` клади в файл (`-d "@body.json"`), не экранируй кавычки в командной строке. Лучше `curl.exe`, не alias `curl`.
- Тесты бэкенда гоняй в контейнере api (образ уже содержит зависимости):

```text
docker compose run --rm --no-deps -v "c:\Users\Karasu322\Desktop\income\backend:/app" api sh -c "pytest && pip install -q ruff && ruff check ."
```

Путь к `backend` поправь под машину. `--no-deps` — тесты на SQLite, Postgres не нужен.
- Фронт: `tsc --noEmit` внутри `npm run build` (Docker `web`). Новых npm‑зависимостей без нужды не добавляй.
- Не клади токен Т‑Банка, `.env`, ключи в git и в ответы.

---

## Стек

| Слой | Что |
| --- | --- |
| Backend | Python 3.12, FastAPI, SQLAlchemy 2 **async**, Alembic, Pydantic v2 |
| Worker | тот же образ, что api; APScheduler |
| DB | PostgreSQL 16 в Docker |
| Frontend | React + Vite + TypeScript, Tailwind v4, TanStack Query, React Router |
| Auth | админ из `.env` + зарегистрированные пользователи со статусами, bcrypt, httpOnly cookie `portfel_session` |
| Invest | пакет `t-tech-investments` с GitLab Т‑Банка (индекс и `--trusted-host` в `backend/requirements.txt`). Импорт: `from t_tech.invest import AsyncClient` с fallback на `tinkoff.invest` |
| Токен | Fernet at rest (`FERNET_KEY`), на фронт не отдаётся |

Порты на хосте (локальный compose): UI **8180**, API **8100**, Postgres **5432**; переопределяются `PORTFEL_WEB_PORT` / `PORTFEL_API_PORT` / `PORTFEL_DB_PORT` в `.env`. Сдвинуты с 8080/8000, потому что на машине пользователя эти порты заняты другими проектами. Внутри Docker‑сети порты прежние: api слушает **8000**, nginx — **80**. Prod‑compose публикует только UI на `127.0.0.1:8080` (за ним прокси на VDS).

---

## Архитектура

```
Браузер :8180 (nginx + статика Vite)
    /        → SPA
    /api/*   → api:8000 (FastAPI)
api  → PostgreSQL
worker → PostgreSQL, Invest API, MOEX ISS (IMOEX)
api  → Invest API (живой синк, цены, дивиденды/купоны, свечи)
```

Поток данных:

1. Настройки: read-only токен → проверка `GetAccounts` → шифрование в `broker_connections`.
2. Синк (кнопка или 08:00/20:00 МСК): счета → операции → инструменты → позиции.
3. После успешного синка: пересчёт дневной истории (свечи + снимки). Прогноз календаря — после планового синка в worker.
4. Дашборд при GET тянет живые `get_last_prices` (таймаут ~8 с); если не вышло — цены с последнего синка.

Контейнеры: `db`, `api` (`alembic upgrade head && uvicorn`), `worker` (`python -m app.worker`), `web`.

---

## Карта репозитория

```
portfel/
  plan.md                 # исходный план v1 (исторический)
  README.md               # запуск для человека, CI/CD
  AGENTS.md               # этот файл
  docker-compose.yml      # локальная сборка из исходников
  docker-compose.prod.yml # образы GHCR
  .env.example
  backend/
    app/main.py           # роутеры
    app/config.py         # Settings из env
    app/db.py             # engine, SessionLocal, get_session
    app/worker.py         # расписание
    app/api/routes/       # HTTP, тонкий слой
    app/api/deps.py       # get_session_user / get_current_user / require_admin
    app/models/           # SQLAlchemy
    app/schemas/          # Pydantic ответы/входы
    app/services/         # вся доменная логика
    alembic/versions/     # 0001…0009
    tests/                # pytest-asyncio, SQLite in-memory
  frontend/
    src/App.tsx           # маршруты
    src/pages/            # экраны
    src/api/              # fetch + типы, credentials: include
    src/components/
    nginx.conf            # SPA + proxy /api/
  .github/workflows/      # ci.yml, release.yml
```

**Где править что**

| Задача | Сначала сюда |
| --- | --- |
| Метрики дашборда, средняя, облигации, кэш | `backend/app/services/portfolio.py` |
| Синк Т‑Банка, идемпотентность операций | `backend/app/services/sync.py`, `invest.py` |
| Типы операций, FIGI валют, DTO | `backend/app/services/invest_types.py` |
| Календарь див/купонов | `backend/app/services/calendar.py` |
| XIRR | `backend/app/services/xirr.py` |
| Снимки стоимости, свечи, IMOEX | `backend/app/services/history.py`, `quotes.py` |
| Категории факт/план | `backend/app/services/categories.py` |
| Отрасли / сектора | `backend/app/services/sectors.py` |
| Шифрование токена | `backend/app/services/crypto.py` |
| Регистрация, статусы, админка, передача портфеля | `backend/app/services/users.py`, `api/deps.py`, `routes/auth.py`, `routes/admin.py` |
| Новая таблица | `app/models/*` + Alembic `000N_*.py` + импорт в `models/__init__.py` и `alembic/env.py` |
| Новый API | `app/api/routes/*.py` + `app/main.py` + `app/schemas/` |
| Новый экран | `frontend/src/pages` + `App.tsx` + `AppLayout.tsx` + `frontend/src/api/` |
| Расписание | `backend/app/worker.py` и/или хвост `run_sync_job` |

Слой routes не должен считать портфель — только auth, сессия, вызов сервиса.

---

## Экраны и API

| UI | API |
| --- | --- |
| `/login` | `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me` |
| `/register` | `POST /api/auth/register` |
| `/admin/requests`, `/admin/users` (только админ) | `GET /api/admin/users?status=&q=`, `POST /api/admin/users/actions`, `GET /api/admin/legacy-portfolio`, `POST /api/admin/legacy-portfolio/transfer` |
| `/` дашборд | `GET /api/dashboard`, `/api/accounts`, `/api/operations`, `/api/history` |
| `/categories` | `GET/POST /api/categories`, `PATCH/DELETE /api/categories/{id}`, `PUT /api/categories/assignments` |
| `/sectors` | `GET /api/sectors` |
| `/calendar` | `GET /api/calendar?refresh=true` |
| `/settings` | `GET/PUT /api/settings/connection`, `POST /api/sync`, `GET /api/sync/runs`, `POST /api/auth/password` |
| — | `GET /api/health`, `GET /api/positions` |

OpenAPI: `http://localhost:8180/api/docs` (через nginx) или `http://localhost:8100/api/docs`.

Сессия: cookie, `SameSite`/`Secure` из настроек. Фронт: `fetch(..., { credentials: "include" })`.

---

## Метрики (не путать)

Это сознательные решения продукта, их нельзя «исправить» на классический cost basis без явной просьбы.

- **Стоимость** = позиции × цена + кэш (всё в RUB через FX).
- **Вложено** = сумма платежей операций типов `CASHFLOW_TYPES` (чистые INPUT минус OUTPUT), **не** себестоимость лотов.
- **Прибыль** = стоимость − вложено.
- **XIRR** = Excel‑подобный XIRR по тем же внешним потокам с **инверсией знака** (ввод для инвестора отрицательный) плюс текущая стоимость на сегодня. Нужны разные даты и оба знака.
- **Пассивный доход (календарь)** = прогноз выплат на 12 месяцев / стоимость **бумаг без кэша**.
- **Доля категории** = стоимость узла (свои бумаги + потомки) / **вся** стоимость портфеля. Цель `%` тоже от всего портфеля. Вложенная цель **не вычитается** из родителя; факт родителя **включает** детей.
- **Доля отрасли** = стоимость бумаг сектора / стоимость **бумаг без кэша** в выбранном скоупе (все счета, один счёт или отмеченные папки).
- Денежные суммы в API — **строки** (`"1234.56"`), не float.

Облигации: котировка Т‑Банка часто **% номинала**. Пересчёт: `quoted_unit_price` + `resolve_bond_nominal` в `portfolio.py`. Не считать сырой `%` рублёвой ценой.

Кэш: несколько FIGI одной валюты дедуплицируются (`unique_positions`). FIGI валют:

```
RUB RUB000UTSTOM | USD BBG0013HGFT4 | EUR BBG0013HJJ31
CNY BBG0013HRTL0 | GBP BBG0013HQ5F0
```

`currency_code_of`: валюта только по этой карте, тикеру‑коду или `UTSTOM`/`UTSTOD`. Не считать валютой FIGI вроде `USDBOND`.

---

## Домен по файлам

### Пользователи и роли — `users.py` + `deps.py`

- Одна таблица `users`: `status` = `pending` / `active` / `frozen` / `rejected`, флаг `is_admin`. Заявка — это строка со `status=pending`, отдельной таблицы нет.
- Админ — запись с `is_admin=true`. `seed_user` ищет её по флагу и при старте синхронизирует логин/пароль с `APP_USERNAME`/`APP_PASSWORD`. Логин админа нельзя занять при регистрации.
- Зависимости: `get_session_user` — любой активный (для `/me`); `get_current_user` — активный **не** админ, админу 403 (все портфельные роуты); `require_admin` — только админ. Статус проверяется на каждом запросе, поэтому заморозка/удаление рвут сессию сразу (401 с причиной).
- Вход: сначала пароль, потом статус (403 «Заявка на рассмотрении» / «Заявка отклонена» / «Аккаунт заморожен»). Логин без учёта регистра.
- Нормализация: логин и почта в нижнем регистре, телефон → `+7XXXXXXXXXX`. Поиск в админке по логину, почте и цифрам телефона (ведущая `8` ≈ `7`).
- Пакетные действия `approve|reject|freeze|unfreeze|delete`: недопустимые переходы и сам админ — в `skipped`. Удаление — `delete(User)`, остальное чистит каскад FK в Postgres.
- Передача портфеля: `transfer_legacy_portfolio` переписывает `user_id` у `broker_connections`, `categories`, `holdings_categories` с админа на активного пользователя без своего подключения и категорий. Нужна была один раз, когда однопользовательский портфель жил на админе.

### Синхронизация — `sync.py` + `invest.py`

- Ручной синк: `POST /api/sync` → `BackgroundTasks` → `run_sync_job`.
- Операции идемпотентны по `(account_id, broker_operation_id)`. Журнал при расхождении с GetPortfolio **не затирается** (заметка в `sync_runs.notes`).
- После **успешного** синка вызывается `rebuild_history(..., force=True)` (ленивый импорт, чтобы не было цикла `sync → history → portfolio → sync`).
- Фоновые job'ы открывают сессию через `from app import db as db_module` и `db_module.SessionLocal`, **не** `from app.db import SessionLocal`. Иначе тесты не подменят фабрику.

### Дашборд — `portfolio.py`

Живые цены, средняя из `remaining_lots` по BUY/SELL, кэш как позиция, карточки + таблица активов. XIRR считается здесь же.

### Категории — `categories.py`

Дерево папок, `holdings_categories` уникален по `(user_id, figi)` (у пользователя бумага в одной папке; у разных пользователей одна и та же бумага независима). Глубина ограничена.

### Отрасли — `sectors.py`

- `GET /api/sectors`: круговые доли по `instruments.sector` (поле Share/Bond/Etf из Invest API, пишется при синке).
- Кэш не входит. Стоимость — из `build_dashboard`. Пироги: «Все счета» + каждый счёт. `holdings[]` — бумаги с сектором для фильтра по категориям на фронте.
- Пустой сектор → «Без отрасли».

### Календарь — `calendar.py`

- Факт: каждый GET пересобирает `accruals` со статусом `received` из операций `INCOME_TYPES` (`DIVIDEND`, `COUPON`, `DIVIDEND_TRANSFER`, `DIV_EXT`).
- Прогноз: `GetDividends` / `GetBondCoupons`, кэш 12 часов, `?refresh=true` сбрасывает. Количество = сумма `Position.quantity` по figi, без кэша.
- Не писать прогноз, если на `(figi, kind, event_date)` уже есть received.
- Сетка UI — **12 месяцев вперёд**; «получено за 12 мес» — скользящие назад.

### История и график — `history.py`, `xirr.py`, `quotes.py`

- `prices_daily`: дневные close по FIGI (Т‑Банк) и ряд `figi="IMOEX"` (MOEX ISS).
- `portfolio_snapshots`: дневные value/cash/securities/invested + imoex_close.
- Реконструкция: проход по операциям по московским датам; кэш из `payment+commission` плюс лоты **иностранной** валюты; бумаги — remaining lots × close (с ffill).
- Если свечей нет — снимок **только сегодня** из текущих позиций (чтобы тесты/первый запуск не строили тысячи пустых дней).
- Последняя точка графика **пиннится** к текущей стоимости дашборда.
- IMOEX на фронте масштабируется к стоимости портфеля на начале выбранного периода (`PortfolioChart.tsx`).
- `GET /api/history?refresh=true` ждёт пересчёт; без флага в проде может запустить фон, в pytest фон **не** стартует (`PYTEST_CURRENT_TEST`).
- Invest API лимит порядка **600 запросов/мин**. Много свечей подряд легко упирается в `RESOURCE_EXHAUSTED`; между FIGI уже есть короткий sleep. Не добавляй без нужды параллельный обстрел `get_last_prices`.

### Worker — `worker.py`

- heartbeat каждые 5 мин
- живые цены в БД каждые 5 мин (`refresh_stored_prices`)
- синк 08:00 и 20:00 МСК, затем `refresh_all_forecasts`
- все три задачи берут подключения через `active_connections_query()` (`sync.py`): только пользователи со `status=active`

---

## Модель данных

Актуальная голова Alembic: **`0009_user_accounts`**. Цепочка: `0001_create_users` → `0002_tinkoff_sync` → `0003_instrument_nominal` → `0004_categories` → `0005_accruals` → `0006_history` → `0007_account_snapshots` → `0008_instrument_sector` → `0009_user_accounts`.

| Таблица | Смысл |
| --- | --- |
| `users` | логин + bcrypt, `email`/`phone` (unique, у админа null), `status`, `is_admin`, `reviewed_at` |
| `broker_connections` | токен Fernet, статус синка, `history_from`; unique `user_id` |
| `accounts` | счета Т‑Банка, unique `(connection_id, broker_account_id)` |
| `instruments` | figi, ticker, тип, валюта, номинал облигации, `sector` |
| `operations` | сырой журнал |
| `positions` | кэш текущего среза GetPortfolio |
| `categories`, `holdings_categories` | дерево и привязка figi, unique `(user_id, figi)` |
| `accruals` | див/купон: received / declared / forecast, unique `(connection_id, source_key)` |
| `prices_daily` | unique `(figi, day)` |
| `portfolio_snapshots` | unique `(connection_id, day)` |
| `sync_runs` | лог синка |

Новая модель: класс в `app/models/`, экспорт в `__init__.py`, импорт в `alembic/env.py` (чтобы metadata видела таблицу), ревизия с `down_revision` на текущий head.

---

## Тесты

- `backend/tests/conftest.py`: SQLite `StaticPool`, подмена `db_module.SessionLocal`. Пользователи: админ `admin` и активный `investor`, оба с паролем `test-password`. `auth_client` вошёл как `investor` (портфельные тесты), `admin_client` — отдельный клиент со своими cookie, вошёл как админ. В одном тесте можно брать оба.
- id пользователя для `begin_manual_sync` бери через `tests/test_sync.py::investor_id`, не хардкодь `1` (это админ).
- Autouse stub: `fetch_daily_candles` / `fetch_imoex` → пусто, чтобы `run_sync_job` не ходил в сеть. В тесте истории stub **переопределяется**.
- Сид портфеля: `tests/test_dashboard.py::_seed` + `tests/test_sync.py::_payload` (SBER 10 × 270, кэш 1500, опционально INPUT).
- Даты в домене патчить `moscow_today` там, **откуда** её берёт код (`app.services.history` и/или `app.services.xirr`).
- `ruff.toml`: E/F/W, E501 игнор. Циклы импортов ловит F821/падение на старте — не импортировать `history` с верхнего уровня `sync.py` или `portfolio.py`.

---

## Типичные ловушки

1. **Циклические импорты.** `history` → `portfolio` (цены, unique_positions). `portfolio` → `xirr`, не в `history`. `sync` импортирует `rebuild_history` только внутри функции.
2. **SessionLocal в тестах.** Только `db_module.SessionLocal`.
3. **Compose без bind mount.** Забыл `--build` — в контейнере старый код.
4. **Знак payment Т‑Банка.** INPUT обычно > 0, BUY < 0, OUTPUT < 0. Для «получено» в календаре берётся `abs(payment)`.
5. **Облигации и валюта.** См. метрики выше.
6. **PowerShell + JSON.** Файл, не строка с `\"`.
7. **Не ходи в Invest API из unit‑тестов.** Мокай `load_invest_data`, `ping_token`, `fetch_last_prices`, свечи, номиналы, дивиденды.
8. **Роли.** Новый портфельный роут — через `get_current_user` (админу 403). Общий для обеих ролей — `get_session_user`. Админский — `require_admin`. Любой запрос к пользовательским данным фильтруй по `user.id`/его подключению: глобальных уникальностей по `figi`/`broker_account_id` больше нет.
9. **Кэш TanStack Query между пользователями.** При входе и выходе фронт делает `queryClient.clear()`, иначе в том же браузере мелькнут данные прошлого пользователя.

---

## Вне скоупа v1 (не делать без запроса)

- Excel‑импорт отчёта Т‑Банка, 3‑НДФЛ, 20 брокеров, крипта
- авторебаланс, look-through фондов
- настройка VDS: Caddy/nginx на хосте, HTTPS, файрвол, бэкапы диска
- Redis/Celery

CI/CD уже есть: PR → ruff/pytest/`npm run build`; пуш в `main` → GHCR + опционально SSH на VDS. Прокси на сервере — зона пользователя.

---

## Чеклист новой фичи

1. Понять, какая метрика/инвариант из раздела «Метрики» затрагивается.
2. Модель + миграция, если нужны данные.
3. Сервис → тонкий route → схема.
4. Тест: 401 без сессии, пустое состояние, счастливый путь на `_seed`, регрессия дашборда если трогали стоимость/вложено.
5. Фронт: `src/api/*`, страница, навигация, русские подписи.
6. `pytest` + `ruff` + сборка фронта.
7. `docker compose up --build -d`, миграция в логах api, проверка `localhost:8180`.
