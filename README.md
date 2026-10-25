# Hermes Agent + Qwen3-TTS VoiceDesign для macOS

Локальный русскоязычный TTS для ответов Hermes Agent на Apple Silicon. Модель: `mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-bf16`.

## Состав

| Файл | Назначение |
| --- | --- |
| `scripts/hermes_tts_server.py` | HTTP-сервер. Держит модель в памяти, по умолчанию слушает `127.0.0.1:8031` и отвечает на `GET /health` и `POST /tts`. |
| `scripts/hermes_tts_client.py` | Адаптер для командного TTS-провайдера Hermes. Отправляет на сервер текст и описание голоса. |
| `scripts/healthcheck.sh` | Проверка `GET /health` из командной строки. |
| `install.sh` | Ставит зависимости, создаёт `.venv` или берёт уже существующий, регистрирует `LaunchAgent`. |
| `uninstall.sh` | Останавливает сервер, затем выгружает и удаляет `LaunchAgent`. Файлы приложения и кэш модели остаются. |
| `config/tts.yaml` | Фрагмент для `~/.hermes/config.yaml`. |

## Требования

- macOS, `arm64`.
- Python 3.10+, рекомендуется 3.12. Системный `python3` из Command Line Tools (3.9) не подходит: `brew install python@3.12` и `PYTHON=python3.12 ./install.sh`.
- `ffmpeg` — только для mp3 (`brew install ffmpeg`).
- Около 4,5 ГБ на диске под модель (1.7B, bf16) и столько же свободной памяти.
- Интернет при каждом старте сервера: он сверяет контрольные суммы модели с Hugging Face. Сама модель не скачивается. Без интернета — [офлайн-режим](#офлайн-режим).

## Установка

```sh
chmod +x install.sh uninstall.sh
./install.sh                                  # ~/Library/Application Support/hermes-qwen3-tts
./install.sh "/opt/tts-ru/hermes-qwen3-tts"   # другой каталог
QWEN_TTS_PORT=8032 ./install.sh               # другой порт
```

Путь установки и значения переменных не должны содержать `&`, `<`, `>` и кавычек: они попадают в plist.

Установщик выполняет четыре шага:

1. Копирует сервер, клиент и `healthcheck.sh` в `<prefix>/scripts/`.
2. Создаёт `<prefix>/.venv` или использует уже существующий.
3. Ставит `mlx-audio[server]==0.6.1` (вместе с ним приходят `fastapi` и `uvicorn`) и `huggingface_hub>=1.10` (в нём есть `hf cache verify`). Версия `mlx-audio` зафиксирована: API модели между выпусками меняется.
4. Регистрирует пользовательскую службу `local.tts-ru.hermes-qwen3-tts`.

Модель установщик не скачивает, это следующий шаг.

> [!WARNING]
> Если в `<prefix>` уже есть `.venv`, установщик ставит пакеты в него и может изменить версии зависимостей. Чтобы не задеть другое окружение, ставьте пакет в отдельный каталог. Если всё же используете существующий `.venv`, сначала сделайте его резервную копию.

## Модель

Сервер сам модель не скачивает и не докачивает: она весит около 4,5 ГБ, качайте её один раз вручную. `hf` ставится в `.venv` установщиком.

```sh
HF="$HOME/Library/Application Support/hermes-qwen3-tts/.venv/bin/hf"   # для своего каталога подставьте свой путь
MODEL=mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-bf16

"$HF" download "$MODEL"                                   # прерванная загрузка продолжится с места остановки
"$HF" cache verify "$MODEL" --fail-on-missing-files       # та же проверка, что делает сервер
```

При старте сервер:

1. проверяет, что порт свободен;
2. проверяет модель командой `hf cache verify --fail-on-missing-files`: все файлы репозитория на месте, sha256 совпадают с Hugging Face. Это читает модель целиком, около 5 с;
3. загружает модель только из кэша (`HF_HUB_OFFLINE=1`).

Если порт занят, модели нет, она повреждена или Hugging Face недоступен (а офлайн-режим не включён), сервер пишет причину в `server.log` и завершается. launchd повторяет запуск каждые 60 с, поэтому после загрузки модели или освобождения порта служба поднимется сама.

### Офлайн-режим

Если интернета нет, а модель уже скачана, отключите проверку контрольных сумм: положите рядом с сервером пустой файл `SKIP_MODEL_VERIFY`.

```sh
touch "$HOME/Library/Application Support/hermes-qwen3-tts/scripts/SKIP_MODEL_VERIFY"   # включить
rm    "$HOME/Library/Application Support/hermes-qwen3-tts/scripts/SKIP_MODEL_VERIFY"   # выключить
```

Файл проверяется при каждом старте сервера; переустановка его не удаляет. С ним сервер:

- не обращается к Hugging Face и пишет в `server.log` предупреждение о пропущенной проверке;
- проверяет только, что модель есть в кэше, и без неё завершается, как обычно;
- не замечает повреждённых файлов: если модель битая, она упадёт при загрузке или синтезе. Когда интернет появится, удалите файл, чтобы проверка снова работала.

Чтобы режим применился к уже запущенному серверу, перезапустите службу (см. «Эксплуатация»).

### Кэш

Кэш по умолчанию — `~/.cache/huggingface`. Если вы держите его в другом месте через `HF_HOME`, задайте эту переменную и при запуске `install.sh`: установщик передаст её службе, launchd не видит окружение вашей оболочки.

## Подключение к Hermes

1. В `config/tts.yaml` замените оба вхождения `/ABSOLUTE/PATH/TO/INSTALL` в поле `command` на каталог установки, например `/Users/<user>/Library/Application Support/hermes-qwen3-tts`. Пишите полный путь без `~` и сохраните двойные кавычки вокруг путей: в пути есть пробел.
2. Перенесите секцию `tts:` в `~/.hermes/config.yaml`.
3. Включите озвучку ответов: в CLI командой `/voice tts`. Подробности — в [документации Hermes](https://hermes-agent.nousresearch.com/docs/user-guide/features/tts).

### Голос

Голос задаётся параметром `voice` у провайдера `qwen3-voice`. Его значение уходит в модель как `instruct`. Описывайте голос по-английски: модель понимает английские описания лучше.

```yaml
tts:
  providers:
    qwen3-voice:
      voice: "Native Russian speaker, female, about 35 years old. Natural modern Russian speech without a foreign accent. Calm, composed and businesslike, like an experienced professional delivering a formal report. Medium-low pitch, even and clear timbre, precise articulation. Steady moderate pace with short pauses between sentences. Neutral, restrained intonation with little emotional variation. Serious and matter-of-fact, without theatrical or dramatic emphasis."
```

В описании можно задать тембр, возраст, темп, дикцию, эмоциональность и манеру подачи. Насколько точно модель их выдержит, зависит от самой модели.

Формат задаётся `output_format`: `wav` или `mp3`. Клиент берёт его из расширения выходного файла.

Тембр одинаков от запроса к запросу, потому что сервер фиксирует `seed` (по умолчанию `42`).

### Переменные окружения

| Переменная | Где | По умолчанию | Назначение |
| --- | --- | --- | --- |
| `QWEN_TTS_MODEL` | сервер | `mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-bf16` | Модель |
| `QWEN_TTS_HOST`, `QWEN_TTS_PORT` | сервер | `127.0.0.1`, `8031` | Адрес |
| `QWEN_TTS_MAX_TOKENS` | сервер | `4096` | Предел длины аудио, около 5,5 мин |
| `QWEN_TTS_LOG_DIR` | сервер | не задана: лог в stderr | Каталог `server.log`; `install.sh` ставит `<prefix>/logs` |
| `QWEN_TTS_LOG_MAX_BYTES` | сервер | `5242880` (5 МБ) | Размер файла лога до ротации |
| `QWEN_TTS_LOG_BACKUPS` | сервер | `3` | Сколько старых файлов хранить |
| `HF_HOME` | сервер | `~/.cache/huggingface` | Кэш Hugging Face; `install.sh` передаёт службе, только если переменная задана |
| `LAUNCH_PATH` | сервер | `/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin` | `PATH` службы, нужен для `ffmpeg` |
| `QWEN_TTS_URL` | клиент, `healthcheck.sh` | `http://127.0.0.1:8031` | Адрес сервера |
| `QWEN_TTS_CLIENT_TIMEOUT` | клиент | `300` | Таймаут запроса, с |
| `QWEN_TTS_LANGUAGE` | клиент | `Russian` | Язык синтеза |

Серверные переменные читает `install.sh` при установке и записывает в `EnvironmentVariables` plist-файла службы. Чтобы их сменить, перезапустите `install.sh` с новыми значениями: правки plist вручную он затрёт.

Если адрес сервера нестандартный, задайте `QWEN_TTS_URL` в окружении, где работает Hermes: клиент запускается как дочерний процесс Hermes и наследует его переменные.

## Эксплуатация

```sh
# состояние сервера
curl -sS http://127.0.0.1:8031/health

# состояние службы
launchctl print "gui/$(id -u)/local.tts-ru.hermes-qwen3-tts"

# журнал (если ставили в другой каталог, подставьте свой путь)
tail -f "$HOME/Library/Application Support/hermes-qwen3-tts/logs/server.log"

# остановить / запустить службу
PLIST="$HOME/Library/LaunchAgents/local.tts-ru.hermes-qwen3-tts.plist"
launchctl bootout   "gui/$(id -u)" "$PLIST"
launchctl bootstrap "gui/$(id -u)" "$PLIST"

# остановить сервер и снять регистрацию службы (запускать из каталога распакованного пакета)
./uninstall.sh
```

Сервер начинает принимать соединения только после проверки и загрузки модели, до этого `curl` получает отказ в соединении.

Бывает, что после изменений генерация не соответствует указаниям промпта, в таком случае - начать новый чат.

### Логи

Файлы лежат в `<prefix>/logs/`:

- `server.log` — журнал сервера и uvicorn, включая трейсбеки. Сервер сам ротирует его по размеру: старые файлы `server.log.1` … `server.log.3`. Предел занятого места — около `QWEN_TTS_LOG_MAX_BYTES × (QWEN_TTS_LOG_BACKUPS + 1)`, по умолчанию 20 МБ.
- `stderr.log` — сырой stderr процесса: нативные падения MLX и предупреждения библиотек. Ротации у launchd нет, поэтому сервер при старте очищает файл, если тот больше `QWEN_TTS_LOG_MAX_BYTES`.

stdout службы направлен в `/dev/null`: сервер в него не пишет.

`uninstall.sh` сначала останавливает сервер (`launchctl bootout`) и ждёт до 30 с, пока процесс завершится. Только после этого он удаляет plist. Если процесс не остановился, plist остаётся на месте, а скрипт выходит с ошибкой. Каталог установки и кэш Hugging Face скрипт не трогает, при необходимости удалите их вручную.

## Ограничения

- Аутентификации нет. Сервер рассчитан на `127.0.0.1`: другой `QWEN_TTS_HOST` откроет его без пароля всем, кто видит этот адрес.
- Потоковой генерации нет: сначала синтезируется весь файл, потом он отдаётся целиком.
- Генерация идёт последовательно, по одному запросу за раз.
- Длина одного фрагмента ограничена `QWEN_TTS_MAX_TOKENS`. Длинный текст Hermes сам режет на части по `max_text_length` (в примере 2000 символов).
- Командный провайдер запускает локальную команду от имени текущего пользователя. Используйте только конфигурацию и файлы, которым доверяете.

## Разработка

```sh
uv run --group dev pre-commit install          # хук перед коммитом
uv run --group dev pre-commit run --all-files  # ruff, markdownlint, shellcheck
uv run --group dev pytest                      # тест клиента без модели
```

История изменений — в [`CHANGELOG.md`](CHANGELOG.md).

## Лицензия

Код — MIT, см. [`LICENSE`](LICENSE). Модель Qwen3-TTS распространяется под собственной лицензией (Apache-2.0, см. карточку модели на Hugging Face).
