# 🌶️ Острый Python — командный квест

Командный квест для практики Python. Решайте задачи по порядку: входные данные приходят с сервера, программа вычисляет ответ и отправляет его обратно в JSON. Прогресс общий для всей команды.

## Как работает задача

1. Запросите входные данные: `GET /api/tasks/{task_id}/input`.
2. Прочитайте объект `input` из ответа и выполните задание.
3. Отправьте ответ: `POST /api/submit` с полями `task_id` и `answer`.
4. При верном ответе сервер подтвердит задачу и выдаст команде её фрагмент ссылки.

`task_id` — строковый номер задачи, например `"1.1"`. Сравнение ответа точное: имена полей, типы значений и вложенность JSON должны совпадать с условием. Число `55` — это число, а не строка `"55"`.

## Адрес и доступные маршруты

Для пробного сервера используется `http://192.144.13.123:8765`.

| Метод и путь | Назначение |
|---|---|
| `GET /api/tasks` | список доступных серверу задач |
| `GET /api/tasks/{task_id}/input` | получить данные конкретной задачи |
| `POST /api/submit` | отправить вычисленный ответ |
| `GET /api/progress` | посмотреть общий прогресс команды |

**Важно:** сейчас сервер настроен только для демонстрационных задач `demo-01` и `demo-02`. Задачи `1.1`–`6.3` описаны в этом репозитории, но их нужно будет отдельно добавить в конфигурацию сервера. До этого запросы по этим ID могут не работать. Сервер пока использует HTTP; не отправляйте через него пароли или личные данные.

## Шаблон программы

В примере используется только стандартная библиотека Python. В `TASK_ID` поставьте номер задачи, а в `answer` сформируйте объект по её условию.

```python
import json
from urllib.request import Request, urlopen

BASE_URL = "http://192.144.13.123:8765"
TASK_ID = "1.1"

# Получаем данные задачи
with urlopen(f"{BASE_URL}/api/tasks/{TASK_ID}/input") as response:
    task = json.load(response)

print("Входные данные:", task["input"])

# Вычислите ответ по условию задачи и укажите нужные поля JSON.
answer = {"change": 55}

# Отправляем ответ на сервер
payload = json.dumps({"task_id": TASK_ID, "answer": answer}).encode("utf-8")
request = Request(
    f"{BASE_URL}/api/submit",
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urlopen(request) as response:
    result = json.load(response)

print(result)
```

В каждой задаче приведены примеры структуры `input` и `answer`. Числа в примерах учебные: при запуске сервер может выдать другие значения. Ответ нужно вычислять по полученным данным, а не копировать пример.

## Уровни

| Уровень | Тема | Задач |
|---|---|---:|
| [1 · Первый укус](tasks/level-1-start/README.md) | ввод, вывод, арифметика | 3 |
| [2 · Развилка](tasks/level-2-fork/README.md) | условия | 3 |
| [3 · Разгон](tasks/level-3-speedup/README.md) | цикл `for` | 3 |
| [4 · Пока не закипит](tasks/level-4-until-boil/README.md) | цикл `while` | 3 |
| [5 · Двойной удар](tasks/level-5-double-hit/README.md) | вложенные циклы и строки | 3 |
| [6 · Список острых](tasks/level-6-hot-lists/README.md) | списки | 3 |

## Все задачи

| ID | Задача |
|---|---|
| 1.1 | [Сдача](tasks/level-1-start/task-1-1-change/README.md) |
| 1.2 | [Пицца на компанию](tasks/level-1-start/task-1-2-pizza/README.md) |
| 1.3 | [Часы и минуты](tasks/level-1-start/task-1-3-hours-minutes/README.md) |
| 2.1 | [Билет в кино](tasks/level-2-fork/task-2-1-cinema/README.md) |
| 2.2 | [Какая оценка](tasks/level-2-fork/task-2-2-grade/README.md) |
| 2.3 | [Високосный год](tasks/level-2-fork/task-2-3-leap-year/README.md) |
| 3.1 | [Таблица умножения](tasks/level-3-speedup/task-3-1-times-table/README.md) |
| 3.2 | [Шагомер](tasks/level-3-speedup/task-3-2-pedometer/README.md) |
| 3.3 | [Обратный отсчёт](tasks/level-3-speedup/task-3-3-countdown/README.md) |
| 4.1 | [Копилка](tasks/level-4-until-boil/task-4-1-piggy-bank/README.md) |
| 4.2 | [Сколько цифр](tasks/level-4-until-boil/task-4-2-digits/README.md) |
| 4.3 | [Бактерии в чашке](tasks/level-4-until-boil/task-4-3-bacteria/README.md) |
| 5.1 | [Лесенка](tasks/level-5-double-hit/task-5-1-stairs/README.md) |
| 5.2 | [Шахматная доска](tasks/level-5-double-hit/task-5-2-chessboard/README.md) |
| 5.3 | [Гласные](tasks/level-5-double-hit/task-5-3-vowels/README.md) |
| 6.1 | [Средний балл](tasks/level-6-hot-lists/task-6-1-average/README.md) |
| 6.2 | [Самый высокий и самый низкий](tasks/level-6-hot-lists/task-6-2-tallest-shortest/README.md) |
| 6.3 | [Топ-3 игроков](tasks/level-6-hot-lists/task-6-3-top3/README.md) |

## Структура репозитория

```text
README.md                         # общий порядок работы и формат API
tasks/<уровень>/README.md         # список задач уровня
tasks/<уровень>/<задача>/README.md # условие, пример входа и пример ответа
```
