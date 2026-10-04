#!/usr/bin/env bash
# ==============================================================================
# OpenFlux Multi-User Gateway & Web UI Installer
# Compatible with: Ubuntu 22.04 / 24.04, Debian 11 / 12 (systemd, x86_64)
# ==============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
SKY='\033[0;36m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Check root permissions
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}[ERROR] Пожалуйста, запустите установщик с правами root:${NC}"
    echo "  sudo bash install.sh"
    exit 1
fi

echo -e "${SKY}${BOLD}"
echo "================================================================================"
echo "          OpenFlux Web UI & Multi-User Gateway — Автоматический установщик     "
echo "================================================================================"
echo -e "${NC}"

INSTALL_DIR="/opt/openflux-web-ui"
CONFIG_DIR="/etc/openflux/users"
RUN_DIR="/run/openflux"
DB_DIR="/etc/openflux"
SCRIPT_SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 1. Detect public IP
echo -e "${SKY}==> [1/8] Определение сетевых параметров сервера...${NC}"
DETECTED_IP=$(curl -s4 --max-time 3 https://ifconfig.me || curl -s4 --max-time 3 https://api.ipify.org || hostname -I | awk '{print $1}')

echo -e "Обнаружен внешний IP сервера: ${GREEN}${BOLD}${DETECTED_IP}${NC}"
read -rp "Введите IP или домен сервера для клиентов [${DETECTED_IP}]: " INPUT_HOST
SERVER_HOST="${INPUT_HOST:-$DETECTED_IP}"

# 2. Admin password setup
echo ""
echo -e "${SKY}==> [2/8] Настройка доступа администратора в веб-панель...${NC}"
read -rp "Задайте пароль администратора (по умолчанию: admin123): " INPUT_PASS
ADMIN_PASS="${INPUT_PASS:-admin123}"

# 3. System packages
echo ""
echo -e "${SKY}==> [3/8] Установка системных зависимостей (Python 3, venv, curl, ufw)...${NC}"
apt-get update -q
apt-get install -y -q python3 python3-venv python3-pip curl ufw systemd

# 4. Preparing directories
echo ""
echo -e "${SKY}==> [4/8] Создание структуры каталогов...${NC}"
mkdir -p "$INSTALL_DIR"
mkdir -p "$CONFIG_DIR"
mkdir -p "$RUN_DIR"
mkdir -p "$DB_DIR"
chmod 700 "$DB_DIR"
chmod 755 "$RUN_DIR"

# 5. Copying application files to /opt/openflux-web-ui
echo ""
echo -e "${SKY}==> [5/8] Копирование компонентов веб-панели в ${INSTALL_DIR}...${NC}"
if [ "$SCRIPT_SRC_DIR" != "$INSTALL_DIR" ]; then
    cp -r "$SCRIPT_SRC_DIR/app" "$INSTALL_DIR/"
    cp -r "$SCRIPT_SRC_DIR/bin" "$INSTALL_DIR/"
    cp -r "$SCRIPT_SRC_DIR/cli" "$INSTALL_DIR/"
    cp -r "$SCRIPT_SRC_DIR/systemd" "$INSTALL_DIR/"
    cp -r "$SCRIPT_SRC_DIR/nginx" "$INSTALL_DIR/"
    cp "$SCRIPT_SRC_DIR/requirements.txt" "$INSTALL_DIR/"
    cp "$SCRIPT_SRC_DIR/run.py" "$INSTALL_DIR/"
    cp "$SCRIPT_SRC_DIR/.env.example" "$INSTALL_DIR/.env.example"
fi

# 6. Install OpenFlux binary
echo ""
echo -e "${SKY}==> [6/8] Установка бинарного ядра OpenFlux...${NC}"
if [ -f "$INSTALL_DIR/bin/openflux-linux" ]; then
    cp "$INSTALL_DIR/bin/openflux-linux" /usr/local/bin/openflux
    chmod +x /usr/local/bin/openflux
    echo -e "${GREEN}✓ Бинарник OpenFlux установлен в /usr/local/bin/openflux${NC}"
else
    echo -e "${YELLOW}[ПРЕДУПРЕЖДЕНИЕ] Скомпилированный бинарник bin/openflux-linux не найден!${NC}"
    echo "Убедитесь, что бинарник /usr/local/bin/openflux установлен вручную."
fi

# Install CLI commands
cp "$INSTALL_DIR/bin/openflux-qr" /usr/local/bin/openflux-qr
cp "$INSTALL_DIR/bin/openflux-mode" /usr/local/bin/openflux-mode
chmod +x /usr/local/bin/openflux-qr /usr/local/bin/openflux-mode
chmod +x "$INSTALL_DIR/cli/show_qr.py" "$INSTALL_DIR/cli/set_mode.py"

# 7. Python virtual environment
echo ""
echo -e "${SKY}==> [7/8] Настройка виртуального окружения Python и зависимостей...${NC}"
if [ ! -d "$INSTALL_DIR/venv" ]; then
    python3 -m venv "$INSTALL_DIR/venv"
fi
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip -q
"$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt" -q

# Initialize database with server host and admin password
"$INSTALL_DIR/venv/bin/python3" -c "
import asyncio, sys
sys.path.insert(0, '$INSTALL_DIR')
from app import database

async def init():
    await database.init_db()
    await database.set_setting('server_host', '$SERVER_HOST')
    await database.set_setting('admin_password', database.hash_password('$ADMIN_PASS'))

asyncio.run(init())
"

# 8. Setup Systemd and UFW
echo ""
echo -e "${SKY}==> [8/8] Настройка служб systemd и фаервола...${NC}"
cp "$INSTALL_DIR/systemd/openflux-ui.service" /etc/systemd/system/openflux-ui.service
cp "$INSTALL_DIR/systemd/openflux@.service" /etc/systemd/system/openflux@.service

systemctl daemon-reload
systemctl enable openflux-ui.service
systemctl restart openflux-ui.service

# Setup UFW if enabled
if command -v ufw >/dev/null 2>&1; then
    if ufw status | grep -q "Status: active"; then
        echo "Открытие диапазона портов 8440-8500/tcp для Session mode..."
        ufw allow 8440:8500/tcp comment 'OpenFlux Session Mode' >/dev/null 2>&1 || true
        ufw allow 8000/tcp comment 'OpenFlux Web UI' >/dev/null 2>&1 || true
    fi
fi

echo ""
echo -e "${GREEN}${BOLD}================================================================================"
echo "          УСТАНОВКА OPENFLUX WEB UI УСПЕШНО ЗАВЕРШЕНА!                        "
echo -e "================================================================================${NC}"
echo ""
echo -e "  🌐 ${BOLD}Локальный адрес панели:${NC}     http://127.0.0.1:8000"
echo -e "  🔑 ${BOLD}Логин администратора:${NC}      admin"
echo -e "  🔒 ${BOLD}Пароль администратора:${NC}     ${ADMIN_PASS}"
echo -e "  🌍 ${BOLD}Хост для клиентов:${NC}         ${SERVER_HOST}"
echo ""
echo -e "  📌 ${BOLD}Управление службой панели:${NC}"
echo "     systemctl status openflux-ui       # Проверить статус"
echo "     systemctl restart openflux-ui      # Перезапустить"
echo "     journalctl -u openflux-ui -f       # Просмотр логов"
echo ""
echo -e "  📱 ${BOLD}Консольные утилиты:${NC}"
echo "     openflux-qr <имя_пользователя>            # Вывести QR-код в терминал"
echo "     openflux-mode <имя> <session|classic>    # Переключить режим работы"
echo ""
echo -e "  🛡️ ${BOLD}Настройка Nginx:${NC}"
echo "     Пример конфигурации обратного прокси доступен в:"
echo "     ${INSTALL_DIR}/nginx/openflux.conf"
echo ""
echo -e "${GREEN}Приятного использования!${NC}"
