# Changelog

Все заметные изменения проекта. Формат — [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/), версии — [SemVer](https://semver.org/lang/ru/).

Раздел «Новое» — изменения после последнего выпуска. При выпуске они переносятся под номер версии.

## [Новое]

### Изменено

- Минимальная версия Python — 3.11, `install.sh` отказывается ставиться на 3.10. Если у вас 3.10, установите `python@3.12` и запустите `PYTHON=python3.12 ./install.sh`.

### Безопасность

- `install.sh` ставит `filelock>=4.2.1`, в том числе в уже существующий `.venv`. В более старых версиях есть уязвимости в `ReadWriteLock` и `SoftFileLock` (GitHub Security Advisories), а исправленные версии не поддерживают Python 3.10.

## [1.1.0] - 2026-10-25

### Добавлено

- Офлайн-режим: если рядом с `hermes_tts_server.py` лежит файл `SKIP_MODEL_VERIFY`, сервер не сверяет контрольные суммы модели с Hugging Face и стартует без интернета. Наличие модели в кэше по-прежнему проверяется.

### Изменено

- `HF_HUB_OFFLINE=1` выставляется в самом начале работы сервера; к Hugging Face обращается только подпроцесс `hf cache verify`.

## 1.0.0 - 2026-10-25

Отдельно не публиковалась, вошла в первый опубликованный выпуск 1.1.0.

### Добавлено

- HTTP-сервер Qwen3-TTS VoiceDesign на MLX: `GET /health`, `POST /tts`, ответ в WAV или MP3, фиксированный `seed` для стабильного тембра.
- Командный провайдер Hermes Agent `hermes_tts_client.py` и фрагмент конфигурации `config/tts.yaml`.
- `install.sh`: служба LaunchAgent, настройки из переменных окружения с проверкой значений, повтор запуска раз в 60 с.
- `uninstall.sh`: останавливает сервер и только потом удаляет LaunchAgent.
- Проверки до загрузки модели: свободен ли порт, цела ли модель (`hf cache verify`). Модель не скачивается автоматически.
- Логи с ротацией по размеру.
- Линтинг (ruff, markdownlint, shellcheck) через pre-commit, CI на GitHub Actions, тест клиента.

[Новое]: https://github.com/pavel-shvagirev/tts-qwen3-ru_srv/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/pavel-shvagirev/tts-qwen3-ru_srv/releases/tag/v1.1.0
