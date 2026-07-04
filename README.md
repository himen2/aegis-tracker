<div align="center">
  <img src="https://github.com/user-attachments/assets/your-logo-url-here" alt="Aegis Tracker Logo" width="200"/>
  <h1>Aegis Tracker 🛡️</h1>
  <p><strong>Некстген-трекинг ML-экспериментов со скоростью света. Написан на Rust.</strong></p>

  [![PyPI version](https://badge.fury.io/py/aegis-tracker.svg)](https://badge.fury.io/py/aegis-tracker)
  [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
  [![Python Versions](https://img.shields.io/pypi/pyversions/aegis-tracker.svg)](https://pypi.org/project/aegis-tracker/)
</div>

<hr/>

**Aegis Tracker** — это современная, легковесная и сверхбыстрая библиотека для логирования метрик машинного обучения. В отличие от других решений, ядро Aegis написано на **Rust 🦀**, что позволяет отправлять метрики и собирать статистику системы **с нулевым влиянием (zero-overhead)** на процесс обучения вашей нейросети.

## ✨ Ключевые особенности

- 🚀 **Rust-Powered Core**: Системные метрики и фоновая отправка данных обрабатываются в изолированных потоках Rust, полностью обходя Python GIL. Ваша модель обучается на максимальной скорости.
- 💾 **Local-First Architecture**: Даже если у вас пропадет интернет или сервер недоступен, Aegis сохранит все метрики в локальную базу данных SQLite и автоматически дошлет их, когда соединение восстановится.
- 📊 **Автоматический сбор системных метрик**: Умный мониторинг CPU, RAM без тяжелых Python-зависимостей вроде `psutil`.
- 🔌 **Plug & Play Интеграции**: Нативные коллбеки для `Keras` и `PyTorch Lightning` (в разработке).
- 🌐 **Бесшовная работа с Jupyter**: Идеальная совместимость с Jupyter Notebook и JupyterLab.

## 📦 Установка

Библиотека распространяется в виде готовых скомпилированных бинарников (Wheels) для Windows, Linux и macOS.

```bash
pip install aegis-tracker
```

## 🚀 Быстрый старт

Использовать Aegis так же просто, как написать `print`. 

```python
import aegis

# 1. Авторизация (сохраняет токен локально)
aegis.login("your_api_token_here")

# 2. Инициализация эксперимента
run = aegis.init(project="my_cool_ai", name="ResNet_Training")

# 3. Логирование метрик внутри вашего цикла обучения
for epoch in range(10):
    loss = train_epoch()
    accuracy = validate()
    
    # Отправка мгновенная! Сетевые запросы обрабатывает фоновый Rust-поток
    run.log({
        "loss": loss,
        "accuracy": accuracy,
        "epoch": epoch
    })
```

## 🧠 Как работает Rust-ядро?

Когда вы вызываете `run.log()`, Aegis не блокирует выполнение Python для отправки HTTP-запроса. Вместо этого:
1. Данные мгновенно передаются в сверхбыструю очередь в памяти (через `crossbeam-channel`).
2. Независимый системный поток на Rust читает эту очередь, упаковывает метрики в батчи (по 50 шт.) и отправляет их на сервер с помощью легковесного HTTP-клиента `ureq`.
3. Никаких лагов сети, никаких задержек от GIL — 100% ресурсов вашего процессора и видеокарты отдаются обучению модели.

## 🛠️ Сборка из исходников (Для разработчиков)

Если вы хотите внести вклад в разработку или собрать ядро под нестандартную архитектуру, вам понадобится Rust и `maturin`:

```bash
# Установите Rust (https://rustup.rs/)
# Установите инструмент сборки
pip install maturin

# Склонируйте репозиторий
git clone https://github.com/your-username/aegis-dist.git
cd aegis-dist

# Скомпилируйте и установите пакет
maturin develop --release
```

## 📄 Лицензия

Проект распространяется под лицензией MIT. Подробности см. в файле [LICENSE](LICENSE).
