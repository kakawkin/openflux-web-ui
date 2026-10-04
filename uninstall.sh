#!/usr/bin/env bash
# ==============================================================================
# OpenFlux Multi-User Gateway & Web UI Uninstaller
# ==============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
SKY='\033[0;36m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}[ERROR] Запустите скрипт удаления с правами root:${NC}"
    echo "  sudo bash uninstall.sh"
    exit 1
fi

echo -e "${RED}${BOLD}"
echo "================================================================================"
echo "          ВНИМАНИЕ! УДАЛЕНИЕ СЛУЖБ И ФАЙЛОВ OPENFLUX WEB UI                    "
echo "================================================================================"
echo -e "${NC}"
read -rp "Вы действительно хотите удалить OpenFlux Web UI с сервера? [y/N]: " CONFIRM
if [[ ! "$CONFIRM" =~ ^[yY]([eE][sS])?$ ]]; then
    echo "Удаление отменено пользователем."
    exit 0
fi

echo -e "${SKY}==> Остановка и отключение служб...${NC}"
systemctl stop openflux-ui.service 2>/dev/null || true
systemctl disable openflux-ui.service 2>/dev/null || true

# Stop all user instances
for service in $(systemctl list-units --type=service --state=running | grep 'openflux@' | awk '{print $1}'); do
    echo "Остановка $service..."
    systemctl stop "$service" 2>/dev/null || true
    systemctl disable "$service" 2>/dev/null || true
done

echo -e "${SKY}==> Удаление systemd служб...${NC}"
rm -f /etc/systemd/system/openflux-ui.service
rm -f /etc/systemd/system/openflux@.service
systemctl daemon-reload

echo -e "${SKY}==> Удаление консольных утилит...${NC}"
rm -f /usr/local/bin/openflux-qr
rm -f /usr/local/bin/openflux-mode

read -rp "Удалить каталог веб-панели (/opt/openflux-web-ui)? [y/N]: " REMOVE_PANEL
if [[ "$REMOVE_PANEL" =~ ^[yY]([eE][sS])?$ ]]; then
    rm -rf /opt/openflux-web-ui
    echo -e "${GREEN}✓ Каталог /opt/openflux-web-ui удален.${NC}"
fi

read -rp "Удалить базу данных и профили пользователей (/etc/openflux)? [y/N]: " REMOVE_CONFIGS
if [[ "$REMOVE_CONFIGS" =~ ^[yY]([eE][sS])?$ ]]; then
    rm -rf /etc/openflux
    rm -rf /run/openflux
    echo -e "${GREEN}✓ Профили и база данных удалены.${NC}"
fi

read -rp "Удалить сам бинарник ядра OpenFlux (/usr/local/bin/openflux)? [y/N]: " REMOVE_BIN
if [[ "$REMOVE_BIN" =~ ^[yY]([eE][sS])?$ ]]; then
    rm -f /usr/local/bin/openflux
    echo -e "${GREEN}✓ Бинарник /usr/local/bin/openflux удален.${NC}"
fi

echo ""
echo -e "${GREEN}${BOLD}✓ Процесс удаления завершен.${NC}"
