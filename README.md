# 🚀 OpenFlux Web UI & Multi-User Panel

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge&logo=python" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/FastAPI-0.115%2B-009688?style=for-the-badge&logo=fastapi" alt="FastAPI">
  <img src="https://img.shields.io/badge/OpenFlux-Go%20Core-00ADD8?style=for-the-badge&logo=go" alt="Go">
  <img src="https://img.shields.io/badge/TailwindCSS-v3-38B2AC?style=for-the-badge&logo=tailwind-css" alt="Tailwind">
  <img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="MIT License">
</p>

Современная веб-панель управления и многопользовательский шлюз для исследовательского инструмента **[OpenFlux](https://github.com/p1neappleXpress/OpenFlux)**. Позволяет развернуть приватный сервер для множества пользователей с автоматическим управлением процессами, ключами, ссылками `openflux://`, QR-кодами, cookies и режимами обхода блокировок.

---

## 📖 Оглавление

1. [Проблема и архитектурное решение](#-проблема-и-архитектурное-решение)
2. [Возможности системы](#-возможности-системы)
3. [Режимы работы: Classic vs Session](#-режимы-работы-classic-vs-session)
4. [Разделение прав доступа](#-разделение-прав-доступа)
5. [Системные требования](#-системные-требования)
6. [Быстрая автоматическая установка (1 команда)](#-быстрая-автоматическая-установка)
7. [Ручная установка](#-ручная-установка)
8. [Настройка Nginx и SSL-сертификатов](#-настройка-nginx-и-ssl)
9. [Консольное управление (CLI)](#-консольное-управление-cli)
10. [Параметры конфигурации (.env)](#-параметры-конфигурации-env)
11. [Диагностика и решение проблем (FAQ)](#-диагностика-и-решение-проблем-faq)
12. [Удаление панели](#-удаление-панели)
13. [Лицензия и благодарности](#-лицензия-и-благодарности)

---

## 💡 Проблема и архитектурное решение

Оригинальное ядро **OpenFlux** в режиме выходной ноды (`--role=exit`) архитектурно рассчитано строго на **1 активного клиента**:
* Сессия держит единый handshake, challenge-ключи и таблицу соединений (conntrack) внутри канала WebSocket документа.
* Если к одной ноде подключаются одновременно два и более клиента, их сессии сбрасываются и возникают постоянные конфликты.

### Решение: архитектура «Instance-per-User»
Данная веб-панель организует пул **изолированных процессов** OpenFlux:
* На каждого добавленного пользователя выделяется отдельный легковесный системный сервис: `openflux@<username>.service`.
* Каждому пользователю назначаются персональный 256-битный ключ AES, собственный URL документа/канала и отдельный TCP-порт.
* Веб-панель общается с ядром через высокоскоростные Unix IPC-сокеты (`/run/openflux/<username>.sock`).
* **Потребление ресурсов:** каждый отдельный процесс OpenFlux на Go потребляет всего **~20–30 МБ RAM**, что позволяет обслуживать десятки пользователей даже на самом бюджетном VPS (1–2 ГБ ОЗУ).

```text
               ┌────────────────────────────────────────────────────────┐
               │                     КЛИЕНТЫ                            │
               │   (iOS TestFlight, Android App, Desktop CLI, Tun)      │
               └───────────────┬────────────────────────┬───────────────┘
                               │                        │
                    HTTPS / WebSocket                 Прямой TCP (Session mode)
                               │                        │
                               ▼                        ▼
               ┌────────────────────────┐      ┌────────────────────────┐
               │ Nginx Reverse Proxy    │      │ UFW Firewall           │
               │ (https://domain/flux)  │      │ (Порты 8440-8500)      │
               └───────────┬────────────┘      └───────────┬────────────┘
                           │                               │
                           ▼                               │
               ┌────────────────────────┐                  │
               │ FastAPI Web UI (:8000) │                  │
               │ (Admin & User Cabinet) │                  │
               └───────────┬────────────┘                  │
                           │ Systemd IPC / Sockets         │
                           ▼                               ▼
  ┌──────────────────────────────────────────────────────────────────────────┐
  │                           VPS UBUNTU / DEBIAN                            │
  │                                                                          │
  │  ┌─────────────────────────┐         ┌─────────────────────────┐         │
  │  │ openflux@alice.service  │         │ openflux@bob.service    │  ...    │
  │  │ (Key, Cookies, Doc URL) │         │ (Key, Cookies, Doc URL) │         │
  │  └───────────┬─────────────┘         └───────────┬─────────────┘         │
  └──────────────┼───────────────────────────────────┼───────────────────────┘
                 ▼                                   ▼
  ┌──────────────────────────────────────────────────────────────────────────┐
  │                 ОБЛАЧНЫЕ ДОКУМЕНТЫ (Яндекс, Mail.ru)                     │
  └──────────────────────────────────────────────────────────────────────────┘
```

---

## ✨ Возможности системы

* 👥 **Полноценный CRUD пользователей:** быстрое создание, редактирование параметров, включение/выключение и удаление профилей.
* 🌐 **Поддержка всех транспортов OpenFlux:** Yandex Telemost (WebRTC SFU, до 40+ Мбит/с), Yandex Docs (WebSocket), Yandex Volga (HTTP relay + WS), Mail.ru Cloud Docs (WS), Yandex Board (WS), Avito Code (ShareDB), Cups.online (Centrifugo).
* 🔄 **Управление транспортом в личном кабинете:** пользователь может самостоятельно менять транспорт и URL прямо из своего кабинета, при этом старые сессионные cookies автоматически сбрасываются во избежание конфликтов протоколов.
* 📖 **Интерактивная шпаргалка/инструкция:** встроенное модальное руководство с подсказками по настройке каждого транспорта прямо в интерфейсе.
* 🛡️ **Полная автономность интерфейса (Zero-CDN):** скрипты Tailwind CSS и иконки Lucide поставляются локально без внешних CDN, что обеспечивает стабильную работу в изолированных сетях и при блокировках.
* 🔄 **Бесшовное переименование профилей:** смена имени пользователя на лету с автомиграцией cookies, ключей шифрования, сокетов и службы systemd.
* 🔐 **Генератор криптостойких ключей:** автоматическая генерация 256-битных HEX-ключей с кнопкой мгновенного копирования.
* 📱 **Быстрое подключение в 1 клик:**
  - Генерация динамического **QR-кода** прямо в браузере (для Android и iOS TestFlight).
  - Генерация официальной ссылки формата `openflux://v1/...` (Raw DEFLATE + Base64 URL-safe).
  - Скачивание готового файла `client.conf` для OpenFlux Desktop / CLI.
* 🍪 **Горячая синхронизация Cookies:** передача cookies на лету через IPC сокет прямо в память работающего процесса ноды без перезагрузки соединения!
* 📊 **Мониторинг в реальном времени:** опрос IPC-сокетов с выводом объемов входящего и исходящего трафика по каждому пользователю.
* 📜 **Встроенный просмотр журналов:** чтение `journalctl` каждого процесса прямо из админ-панели в реальном времени.
* 🎨 **Современный адаптивный интерфейс:** чистый UI на Tailwind CSS и Lucide Icons с поддержкой светлой и тёмной темы.
* ⚙️ **Управление настройками из UI:** модальное окно изменения публичного хоста/домена сервера и смены пароля администратора.

---

## 🚚 Поддерживаемые транспорты

| Транспорт | Протокол маскировки | Скорость | Особенности и настройка |
|---|---|---|---|
| **Яндекс Телемост** (`telemost`) | WebRTC SFU / Media stream (`StripedTransport`) | **До 40+ Мбит/с** | 🏆 **Рекомендуемый.** Максимальная скорость скачивания. Создаётся ссылка на встречу на `telemost.yandex.ru`, не требует файлов на Диске. |
| **Яндекс Документы** (`yandex`) | WebSocket / Share edit | До 10–15 Мбит/с | Классический обход через публичный текстовый документ или таблицу на Яндекс Диске с правами редактирования. |
| **Яндекс Volga** (`vyandex`) | HTTP Relay + WebSocket | До 10 Мбит/с | Транспорт Volga через Яндекс Диск с регулярным HTTP polling. |
| **Mail.ru Документы** (`mailru`) | WebSocket Cloud Office | До 10–15 Мбит/с | Обход через совместное редактирование DOCX/XLSX в Облаке Mail.ru. |
| **Авито Код** (`avito`) | ShareDB / OT stream | До 5–10 Мбит/с | Сессия совместного кода на платформе `code.avito.ru`. |
| **Яндекс Доски** (`boards`) | WebSocket | До 5–10 Мбит/с | Публичная доска на сервисе `boards.yandex.ru`. |
| **Cups.online** (`cupsonline`) | Centrifugo WebSocket | До 5–10 Мбит/с | Комнаты собеседований на платформе `cups.online`. |

---

## 🔀 Режимы работы: Classic vs Session

Каждому пользователю в любой момент доступно переключение между двумя режимами:

| Параметр | 🟢 Classic (Только документы) | 🔵 Session (С прямым портом / Куки) |
|---|---|---|
| **Принцип работы** | Трафик передается **исключительно** через облачные документы (Yandex Docs, Mail.ru, Volga, Boards, Cups.online). | Нода открывает прямой TCP-порт на сервере (например, `8441`). Клиент сначала соединяется напрямую, а затем через документ. |
| **Скрытность** | **Максимальная:** на сервере нет открытых нестандартных портов, трафик неотличим от работы в веб-редакторе. | **Средняя:** на сервере открыт TCP порт из диапазона 8440–8500. |
| **Решение SmartCaptcha** | Требует заранее сохраненных cookies. При запросе капчи Яндексом нода не сможет передать ее клиенту. | **Автоматическое:** капча передается в мобильное приложение (WebView), юзер решает ее за 2 секунды, куки `spravka` сохраняются на сервере. |
| **Рекомендация** | Основной постоянный режим после первичной авторизации. | Используется для первой настройки или при сбросе/истечении cookies Яндекса. |

---

## 🛡️ Разделение прав доступа

Система четко разграничивает панель управления и клиентский доступ:

### 1. Кабинет администратора (`/dashboard`)
* **Логин:** `admin` (или оставить пустым)
* **Пароль:** пароль, заданный при установке (или изменённый в настройках)
* **Возможности:**
  - Создание и редактирование пользователей с выбором любого из 7 транспортов (Telemost, Yandex, Volga, Mail.ru, Avito, Boards, Cups.online).
  - Интерактивная справка по настройке каждого транспорта.
  - Переименование профилей, удаление, принудительный перезапуск.
  - Назначение прямых портов и ручная вставка cookies.
  - Мониторинг всех служб, памяти сервера и трафика всех пользователей.
  - Просмотр системных журналов служб в реальном времени.
  - Глобальные настройки хоста и пароля панели.

### 2. Личный кабинет пользователя (`/my`)
* **Логин:** `<имя_профиля>` (например, `alice` или `damir`)
* **Пароль:** по умолчанию равен имени профиля (пользователь может задать свой личный пароль).
* **Возможности:**
  - Сканирование личного QR-кода и копирование ссылки `openflux://v1/...`.
  - Скачивание файла `client.conf` для настольного клиента или роутера.
  - **Самостоятельный выбор и смена транспорта** (например, мгновенный переход на Yandex Telemost) с автоматическим сбросом устаревших cookies.
  - Встроенная **интерактивная инструкция** («Как настроить?») по получению ссылок для выбранного транспорта.
  - Самостоятельное переключение между режимами **Classic** ↔ **Session**.
  - Перезапуск личной службы `openflux@<username>`.
  - Изменение персонального пароля для входа в кабинет.
  - *Безопасность:* доступ к чужим профилям, удалению или созданию заблокирован (403 Forbidden).

---

## 💻 Системные требования

* **Операционная система:** Ubuntu 22.04 LTS / 24.04 LTS или Debian 11 / 12 (архитектура x86_64 / amd64).
* **Права:** root доступ (sudo).
* **Оперативная память:** от 512 МБ (рекомендуется 1 ГБ+).
* **Сетевой стек:** поддержка `systemd` и утилиты `ufw` (или iptables).

---

## ⚡ Быстрая автоматическая установка

Установка выполняется одной командой на вашем сервере:

```bash
git clone https://github.com/kakawkin/openflux-web-ui.git /opt/openflux-web-ui
cd /opt/openflux-web-ui
sudo bash install.sh
```

### Что сделает скрипт `install.sh`:
1. Автоматически определит публичный IPv4-адрес вашего сервера.
2. Предложит ввести имя домена / IP и задать надёжный пароль администратора.
3. Установит все зависимости: Python 3, `venv`, pip, `curl`, `ufw`, `systemd`.
4. Развернет статический бинарник OpenFlux в `/usr/local/bin/openflux`.
5. Создаст виртуальное окружение Python и установит FastAPI-пакеты.
6. Инициализирует базу данных SQLite (`/etc/openflux/panel.db`).
7. Зарегистрирует и запустит системные службы `openflux-ui` и шаблон `openflux@`.
8. Настроит фаервол UFW: откроет порты `8440:8500/tcp` для Session mode.
9. Установит глобальные консольные утилиты `openflux-qr` и `openflux-mode`.

После завершения скрипт выведет готовые ссылки для входа и учетные данные!

---

## 🛠️ Ручная установка

Если вы предпочитаете настраивать систему пошагово:

```bash
# 1. Обновление пакетов и установка зависимостей
sudo apt update && sudo apt install -y python3 python3-venv python3-pip curl ufw systemd

# 2. Создание каталогов
sudo mkdir -p /opt/openflux-web-ui /etc/openflux/users /run/openflux
sudo chmod 700 /etc/openflux

# 3. Клонирование репозитория
sudo git clone https://github.com/kakawkin/openflux-web-ui.git /opt/openflux-web-ui

# 4. Установка бинарника ядра OpenFlux
sudo cp /opt/openflux-web-ui/bin/openflux-linux /usr/local/bin/openflux
sudo chmod +x /usr/local/bin/openflux

# 5. Настройка Python venv
cd /opt/openflux-web-ui
sudo python3 -m venv venv
sudo ./venv/bin/pip install --upgrade pip
sudo ./venv/bin/pip install -r requirements.txt

# 6. Регистрация systemd служб
sudo cp systemd/openflux-ui.service /etc/systemd/system/
sudo cp systemd/openflux@.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now openflux-ui.service

# 7. Установка консольных команд
sudo cp bin/openflux-qr /usr/local/bin/openflux-qr
sudo cp bin/openflux-mode /usr/local/bin/openflux-mode
sudo chmod +x /usr/local/bin/openflux-qr /usr/local/bin/openflux-mode
```

---

## 🔒 Настройка Nginx и SSL

По умолчанию панель слушает локальный адрес `127.0.0.1:8000`. Для безопасного доступа по HTTPS рекомендуется настроить обратный прокси через Nginx.

### Вариант 1: Размещение по пути `https://yourdomain.com/flux`
Добавьте следующий блок в файл конфигурации вашего домена (например, в `/etc/nginx/sites-available/default` внутри секции `server { ... }`):

```nginx
location /flux {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto https;
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
}
```

### Вариант 2: Отдельный поддомен `https://flux.yourdomain.com`
Создайте файл `/etc/nginx/sites-available/openflux.conf`:

```nginx
server {
    listen 80;
    server_name flux.yourdomain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name flux.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/flux.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/flux.yourdomain.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }
}
```

Активируйте конфиг и получите бесплатный SSL-сертификат:
```bash
sudo ln -s /etc/nginx/sites-available/openflux.conf /etc/nginx/sites-enabled/
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d flux.yourdomain.com
sudo nginx -t && sudo systemctl reload nginx
```

---

## 📟 Консольное управление (CLI)

После установки на сервере доступны удобные команды для работы прямо из SSH-терминала:

### 1. Вывод QR-кода в терминал:
```bash
openflux-qr <имя_пользователя>
```
*Генерирует ASCII QR-код прямо в окне консоли и выводит готовую ссылку `openflux://v1/...`.*

### 2. Смена режима работы пользователя:
```bash
openflux-mode <имя_пользователя> session   # Переключить в Session mode
openflux-mode <имя_пользователя> classic   # Переключить в Classic mode
```
*Автоматически перегенерирует конфигурацию `.conf` и перезапустит службу `openflux@<username>`.*

### 3. Управление системными службами:
```bash
# Статус веб-панели
systemctl status openflux-ui

# Просмотр логов панели
journalctl -u openflux-ui -f

# Перезапуск службы конкретного пользователя (например, alice)
systemctl restart openflux@alice

# Просмотр логов соединения пользователя
journalctl -u openflux@alice -n 50 --no-pager
```

---

## ⚙️ Параметры конфигурации (.env)

Переменные окружения можно переопределять в `/opt/openflux-web-ui/.env` или в systemd-сервисе:

| Переменная | По умолчанию | Описание |
|---|---|---|
| `OPENFLUX_HOST` | `127.0.0.1` | Локальный интерфейс для Uvicorn |
| `OPENFLUX_PORT` | `8000` | Внутренний порт веб-панели |
| `OPENFLUX_DB_PATH` | `/etc/openflux/panel.db` | Путь к базе данных SQLite |
| `OPENFLUX_CONF_DIR` | `/etc/openflux/users` | Каталог файлов конфигураций пользователей (`.conf`, `.key`) |
| `OPENFLUX_SERVER_HOST` | *(автоопределение)* | IP или домен, подставляемый в ссылки клиентов и QR-коды |
| `OPENFLUX_ADMIN_PASSWORD` | `admin123` | Пароль администратора при первой инициализации БД |

---

## ❓ Диагностика и решение проблем (FAQ)

### 1. Клиент не подключается в режиме Classic, в логах: `SmartCaptcha detected`
* **Причина:** Яндекс запросил прохождение проверки на робота (SmartCaptcha). В режиме *Classic* нода не открывает порт для прямого соединения и не может переслать окно капчи в приложение клиента.
* **Решение:**
  1. В панели управления переключите пользователя в режим **Session**.
  2. Отсканируйте обновленный QR-код в мобильном приложении.
  3. Нажмите подключение: на экране телефона откроется окно SmartCaptcha.
  4. Пройдите капчу: файл `/etc/openflux/users/<username>-cookies.json` автоматически запишется на сервере.
  5. Переключите пользователя обратно в режим **Classic**. Нода продолжит работу через Яндекс.Документ скрытно без открытых портов.

### 2. Клиент не подключается в режиме Session (таймаут)
* **Причина:** Порт прямого подключения заблокирован фаерволом (UFW / iptables / Security Group облачного провайдера).
* **Решение:**
  Убедитесь, что порты `8440-8500/tcp` открыты:
  ```bash
  sudo ufw allow 8440:8500/tcp
  sudo ufw status verbose
  ```
  *(Если ваш сервер находится в AWS, Oracle Cloud, GCP, Hetzner или VK Cloud, обязательно разрешите эти порты в веб-консоли провайдера).*

### 3. Где хранятся ключи и конфигурации?
* База данных: `/etc/openflux/panel.db`
* Конфиги нод: `/etc/openflux/users/<username>.conf`
* Ключи AES-256: `/etc/openflux/users/<username>.key`
* Авторизационные cookies: `/etc/openflux/users/<username>-cookies.json`
* Unix сокеты: `/run/openflux/<username>.sock`

---

## 🗑️ Удаление панели

Для чистого и безопасного удаления выполните:

```bash
cd /opt/openflux-web-ui
sudo bash uninstall.sh
```

Интерактивный мастер корректно остановит все службы, удалит файлы systemd и предложит сохранить или удалить базу данных с пользователями.

---

## 📜 Лицензия и благодарности

* Проект распространяется под открытой лицензией **MIT License**. Подробнее см. в файле [LICENSE](LICENSE).
* Ядро сетевого стека создано разработчиками проекта **[OpenFlux](https://github.com/p1neappleXpress/OpenFlux)**.
