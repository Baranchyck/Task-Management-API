# Task Management API

REST API сервіс для управління задачами на базі FastAPI, SQLAlchemy 2.0 (asyncpg), PostgreSQL та Docker Compose.

---

## 🚀 Швидкий запуск

1. Створіть файл `.env` (можна скопіювати з прикладу):
   ```bash
   cp .env.example .env
   ```

2. Запустіть сервіси через Docker Compose:
   ```bash
   docker compose up --build -d
   ```
   *База даних і додаток піднімуться автоматично, міграції Alembic застосуються при старті.*

3. Відкрийте інтерактивну документацію Swagger UI:
   * **Swagger UI:** [http://localhost:8000/docs](http://localhost:8000/docs)
   * **ReDoc:** [http://localhost:8000/redoc](http://localhost:8000/redoc)
   * **Healthcheck:** [http://localhost:8000/health](http://localhost:8000/health)

---

## 🧪 Запуск тестів

Тести запускаються в ізольованій тестовій базі `tracker_test_db`:

```bash
docker compose exec api pytest -v
```

---

## ⚙️ Змінні середовища (.env)

| Змінна | Опис | Значення за замовчуванням |
|---|---|---|
| `PROJECT_NAME` | Назва проєкту | `Task Management API` |
| `POSTGRES_USER` | Користувач PostgreSQL | `postgres` |
| `POSTGRES_PASSWORD` | Пароль PostgreSQL | `postgres` |
| `POSTGRES_HOST` | Хост бази даних | `db` (для Docker) / `localhost` (локально) |
| `POSTGRES_PORT` | Порт PostgreSQL | `5432` |
| `POSTGRES_DB` | Назва бази даних | `tracker_db` |
| `SECRET_KEY` | Секретний ключ для JWT | `supersecretjwtkey...` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Термін дії JWT токена | `1440` (24 години) |
| `OVERDUE_CHECK_INTERVAL_SECONDS` | Інтервал перевірки прострочених задач | `60` секунд |

---

## 📋 Прийняті рішення та бізнес-правила

1. **Активні статуси:** `Backlog`, `In Progress`, `Review`. (Todo = Backlog).
2. **Ліміт активних задач:** виконавець (`assignee_id`) може мати максимум **10 активних задач**. Перевіряється при створенні задачі та при зміні виконавця.
3. **Таблиця переходів статусів:**
   * `Backlog` ➔ `In Progress`, `Cancelled`
   * `In Progress` ➔ `Review`, `Cancelled`
   * `Review` ➔ `Done`
   * `Done` / `Cancelled` — термінальні статуси (вихід заборонено, редагування заборонено).
4. **Спеціальні правила переходів та дій:**
   * Перехід у `Done` заборонений, якщо немає виконавця або дедлайн прострочено (`deadline < now`).
   * У статусах `Review` та `Done` заборонено змінювати виконавця.
   * Видалення задачі заборонене у статусах `In Progress` та `Review`.
   * Редагувати і видаляти задачу може тільки автор.
   * Змінювати статус може автор або призначений виконавець.
5. **Фонова задача автоскасування:**
   * Працює через `asyncio.create_task` у `lifespan` додатку з коректним graceful shutdown (`task.cancel()`).
   * Скасовує всі задачі з `deadline < now`, що не знаходяться в `Done` або `Cancelled` (включно з `Review`), виконуючи один bulk `UPDATE` без вивантаження в пам'ять.
6. **Пагінація та сортування:**
   * Пагінація: `limit` / `offset` (відповідь `{ items, total, limit, offset }`).
   * Сортування пріоритетів через SQL `CASE (High=3, Medium=2, Low=1)`.
   * Пошук `q` через `ILIKE` за назвою та описом.

---

## 📌 Основні ендпоінти API

* `POST /auth/register` — реєстрація користувача.
* `POST /auth/login` — авторизація (OAuth2 Password Request Form, сумісний з кнопкою Authorize в Swagger).
* `GET /auth/me` — інформація про поточного користувача.
* `POST /tasks` — створення задачі.
* `GET /tasks` — список задач з пошуком `q`, фільтрами, сортуванням та пагінацією.
* `GET /tasks/overdue` — список прострочених задач.
* `GET /tasks/stats` — SQL-агрегована статистика задач (по статусах, пріоритетах, active та overdue).
* `GET /tasks/{id}` — перегляд задачі за ID.
* `PATCH /tasks/{id}` — редагування задачі (без зміни статусу).
* `PATCH /tasks/{id}/status` — зміна статусу задачі.
* `DELETE /tasks/{id}` — видалення задачі.
* `POST /tasks/{id}/comments` — додати коментар до задачі (дозволено в будь-якому статусі).
* `GET /tasks/{id}/comments` — отримати коментарі до задачі з пагінацією.
