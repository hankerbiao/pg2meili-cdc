#!/bin/bash

# 配置部分
SERVICE_NAME="UniData"
PID_FILE="unidata.pid"
LOG_FILE="app.log"
HOST="0.0.0.0"
PORT="8000"

# 获取脚本所在目录的绝对路径
WORK_DIR=$(cd "$(dirname "$0")" && pwd)
PID_PATH="$WORK_DIR/$PID_FILE"
LOG_PATH="$WORK_DIR/$LOG_FILE"

# 检查 uv 是否存在
if ! command -v uv &> /dev/null; then
    echo "错误: 未找到 uv 命令，请先安装 uv"
    exit 1
fi

start() {
    if [ -f "$PID_PATH" ]; then
        PID=$(cat "$PID_PATH")
        if ps -p $PID > /dev/null 2>&1; then
            echo "$SERVICE_NAME 正在运行中 (PID: $PID)"
            return
        else
            echo "PID 文件存在但进程未运行，正在清理..."
            rm "$PID_PATH"
        fi
    fi

    echo "正在启动 $SERVICE_NAME ..."
    cd "$WORK_DIR"
    
    # 尝试从 .env 读取端口 (简单读取，不做复杂解析)
    if [ -f .env ]; then
        ENV_PORT=$(grep "^SERVER_PORT=" .env | cut -d '=' -f2 | tr -d '"' | tr -d "'" | tr -d ':')
        if [ ! -z "$ENV_PORT" ]; then
            PORT=$ENV_PORT
        fi
    fi
    
    # 使用 uv 启动 uvicorn
    # --host 0.0.0.0 --port $PORT
    nohup uv run uvicorn app.main:app --host "$HOST" --port "$PORT" > "$LOG_PATH" 2>&1 &
    
    PID=$!
    echo $PID > "$PID_PATH"
    echo "$SERVICE_NAME 已启动 (PID: $PID, Port: $PORT)"
    echo "日志文件: $LOG_PATH"
}

stop() {
    if [ ! -f "$PID_PATH" ]; then
        echo "$SERVICE_NAME 未运行 (PID 文件不存在)"
        return
    fi

    PID=$(cat "$PID_PATH")
    echo "正在停止 $SERVICE_NAME (PID: $PID) ..."
    
    if ps -p $PID > /dev/null 2>&1; then
        kill $PID
        
        # 等待进程退出
        TIMEOUT=10
        COUNT=0
        while ps -p $PID > /dev/null 2>&1; do
            sleep 1
            ((COUNT++))
            if [ $COUNT -ge $TIMEOUT ]; then
                echo "进程未响应，正在强制停止..."
                kill -9 $PID
                break
            fi
        done
        echo "$SERVICE_NAME 已停止"
    else
        echo "进程不存在，正在清理 PID 文件..."
    fi
    
    rm -f "$PID_PATH"
}

status() {
    if [ -f "$PID_PATH" ]; then
        PID=$(cat "$PID_PATH")
        if ps -p $PID > /dev/null 2>&1; then
            echo "$SERVICE_NAME 正在运行 (PID: $PID)"
            echo "--------------------------------"
            echo "最近 10 行日志:"
            tail -n 10 "$LOG_PATH"
        else
            echo "$SERVICE_NAME 未运行 (PID 文件存在但进程丢失)"
        fi
    else
        echo "$SERVICE_NAME 未运行"
    fi
}

log() {
    if [ -f "$LOG_PATH" ]; then
        tail -f "$LOG_PATH"
    else
        echo "日志文件不存在: $LOG_PATH"
    fi
}

case "$1" in
    start)
        start
        ;;
    stop)
        stop
        ;;
    restart)
        stop
        sleep 1
        start
        ;;
    status)
        status
        ;;
    log)
        log
        ;;
    *)
        echo "用法: $0 {start|stop|restart|status|log}"
        exit 1
        ;;
esac
