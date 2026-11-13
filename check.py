#!/usr/bin/env python3
"""Проверка solve.py на примерах из условия.

Примеры запуска (из корня репозитория):
    python check.py 1.1      # одна задача
    python check.py 1        # весь уровень 1
    python check.py          # все задачи
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "tasks"
ENV = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")


def find_tasks(selector):
    tasks = sorted(ROOT.glob("level-*/task-*"))
    if selector is None:
        return tasks
    prefix = "task-" + selector.replace(".", "-") + "-"
    return [t for t in tasks if t.name.startswith(prefix)]


def lines(text):
    return [l.rstrip() for l in text.strip().splitlines()]


def check_task(task):
    examples = json.loads((task / "examples.json").read_text(encoding="utf-8"))
    title = (task / "README.md").read_text(encoding="utf-8").splitlines()[0].lstrip("# ").strip()
    print(title)
    passed = 0
    for i, ex in enumerate(examples, 1):
        try:
            res = subprocess.run(
                [sys.executable, str(task / "solve.py")],
                input=ex["input"] + "\n",
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=5,
                env=ENV,
            )
        except subprocess.TimeoutExpired:
            print("  ❌ Пример %d: программа думает дольше 5 секунд" % i)
            continue
        if res.returncode != 0:
            err = res.stderr.strip().splitlines()
            print("  ❌ Пример %d: ошибка в программе: %s" % (i, err[-1] if err else "неизвестная"))
            continue
        got, want = lines(res.stdout), lines(ex["output"])
        if got == want:
            print("  ✅ Пример %d" % i)
            passed += 1
        else:
            print("  ❌ Пример %d: ответ не совпал" % i)
            print("     ждали:  " + " | ".join(want))
            print("     у тебя: " + (" | ".join(got) if got else "(ничего не напечатано)"))
    return passed == len(examples)


def main():
    selector = sys.argv[1] if len(sys.argv) > 1 else None
    tasks = find_tasks(selector)
    if not tasks:
        print("Не нашёл такую задачу. Пример запуска: python check.py 1.1")
        sys.exit(1)
    ok = 0
    for t in tasks:
        if check_task(t):
            ok += 1
        print()
    print("Итого: примеры проходят %d из %d задач" % (ok, len(tasks)))
    if ok == len(tasks):
        print("🔥 Все примеры сошлись! Но скрытые тесты строже: проверь граничные случаи.")


if __name__ == "__main__":
    main()
