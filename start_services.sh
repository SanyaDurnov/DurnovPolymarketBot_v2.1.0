#!/bin/bash
# Startup script for Polymarket Bot V2 services
#
# This script helps you start all required services in the correct order.
# Each service runs in the background with output redirected to log files.
#
# Usage:
#   ./start_services.sh        # Start all services
#   ./start_services.sh stop   # Stop all services
#   ./start_services.sh status # Check service status

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

# Ensure logs directory exists
mkdir -p logs

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# PID file locations
PRICE_COLLECTOR_PID="logs/price_collector.pid"
MARKET_SERVICE_PID="logs/market_service.pid"
TRADING_BOT_PID="logs/trading_bot.pid"

# Function to start a service
start_service() {
    local name=$1
    local command=$2
    local pid_file=$3
    local log_file=$4

    if [ -f "$pid_file" ] && kill -0 $(cat "$pid_file") 2>/dev/null; then
        echo -e "${YELLOW}⚠️  $name is already running (PID: $(cat $pid_file))${NC}"
        return
    fi

    echo -e "${GREEN}🚀 Starting $name...${NC}"
    nohup $command > "$log_file" 2>&1 &
    echo $! > "$pid_file"
    echo -e "${GREEN}✅ $name started (PID: $(cat $pid_file), logs: $log_file)${NC}"
}

# Function to stop a service
stop_service() {
    local name=$1
    local pid_file=$2

    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if kill -0 $pid 2>/dev/null; then
            echo -e "${YELLOW}🛑 Stopping $name (PID: $pid)...${NC}"
            kill $pid
            rm "$pid_file"
            echo -e "${GREEN}✅ $name stopped${NC}"
        else
            echo -e "${YELLOW}⚠️  $name PID file exists but process is not running${NC}"
            rm "$pid_file"
        fi
    else
        echo -e "${YELLOW}⚠️  $name is not running${NC}"
    fi
}

# Function to check service status
check_status() {
    local name=$1
    local pid_file=$2

    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if kill -0 $pid 2>/dev/null; then
            echo -e "${GREEN}✅ $name is running (PID: $pid)${NC}"
        else
            echo -e "${RED}❌ $name PID file exists but process is not running${NC}"
        fi
    else
        echo -e "${RED}❌ $name is not running${NC}"
    fi
}

# Start all services
start_all() {
    echo -e "${GREEN}==============================================================${NC}"
    echo -e "${GREEN}🚀 Starting Polymarket Bot V2 Services${NC}"
    echo -e "${GREEN}==============================================================${NC}"
    echo ""

    # 1. Start ChainlinkPriceCollector
    echo -e "${GREEN}[1/3] ChainlinkPriceCollector${NC}"
    start_service \
        "ChainlinkPriceCollector" \
        "python3 -u -m app.connectors.chainlink_price_collector" \
        "$PRICE_COLLECTOR_PID" \
        "logs/price_collector.log"
    echo ""

    # 2. Start Market Service
    echo -e "${GREEN}[2/3] Market Service${NC}"
    start_service \
        "Market Service" \
        "python3 -u market_service.py" \
        "$MARKET_SERVICE_PID" \
        "logs/market_service.log"
    echo ""

    # Wait a bit for market service to fetch initial data
    echo -e "${YELLOW}⏳ Waiting 5 seconds for market service to fetch initial data...${NC}"
    sleep 5

    # 3. Start Trading Bot (web UI + trading logic)
    echo -e "${GREEN}[3/3] Trading Bot (Web UI)${NC}"
    start_service \
        "Trading Bot" \
        "python3 -u main.py --mode web" \
        "$TRADING_BOT_PID" \
        "logs/trading_bot.log"
    echo ""

    echo -e "${GREEN}==============================================================${NC}"
    echo -e "${GREEN}✅ All services started!${NC}"
    echo -e "${GREEN}==============================================================${NC}"
    echo ""
    echo -e "${YELLOW}📊 Web UI:${NC} http://localhost:8000"
    echo -e "${YELLOW}📝 Logs:${NC} tail -f logs/*.log"
    echo -e "${YELLOW}📈 Status:${NC} ./start_services.sh status"
    echo -e "${YELLOW}🛑 Stop:${NC} ./start_services.sh stop"
    echo ""
}

# Stop all services
stop_all() {
    echo -e "${RED}==============================================================${NC}"
    echo -e "${RED}🛑 Stopping Polymarket Bot V2 Services${NC}"
    echo -e "${RED}==============================================================${NC}"
    echo ""

    stop_service "Trading Bot" "$TRADING_BOT_PID"
    stop_service "Market Service" "$MARKET_SERVICE_PID"
    stop_service "ChainlinkPriceCollector" "$PRICE_COLLECTOR_PID"

    echo ""
    echo -e "${GREEN}✅ All services stopped${NC}"
    echo ""
}

# Show status of all services
show_status() {
    echo -e "${GREEN}==============================================================${NC}"
    echo -e "${GREEN}📊 Polymarket Bot V2 Service Status${NC}"
    echo -e "${GREEN}==============================================================${NC}"
    echo ""

    check_status "ChainlinkPriceCollector" "$PRICE_COLLECTOR_PID"
    check_status "Market Service" "$MARKET_SERVICE_PID"
    check_status "Trading Bot" "$TRADING_BOT_PID"

    echo ""
}

# Main command handler
case "${1:-start}" in
    start)
        start_all
        ;;
    stop)
        stop_all
        ;;
    restart)
        stop_all
        sleep 2
        start_all
        ;;
    status)
        show_status
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status}"
        exit 1
        ;;
esac
