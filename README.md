# Aegis Tracker

Aegis — это библиотека для трекинга метрик и мониторинга ваших ML-экспериментов.

## Установка

```bash
pip install git+https://github.com/himen2/aegis-tracker.git
```

## Быстрый старт

Библиотека полностью совместима с Python скриптами, **Jupyter Notebook** и **JupyterLab**.

Интеграция занимает всего 3 строчки кода:

```python
import aegis

aegis.login("aegis_live_...")
run = aegis.init(project="my_project", name="experiment_1", config={"lr": 0.001})

for epoch in range(50):
    run.log({"loss": 0.5, "accuracy": 0.85})

run.finish()
```

### Поддержка фреймворков

Для PyTorch, Keras и Sklearn есть готовые коллбеки (см. документацию в веб-версии Aegis).
