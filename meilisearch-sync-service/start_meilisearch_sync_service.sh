#!/bin/bash

# 配置部分
SERVICE_NAME="meilisearch-sync-service"
BINARY_NAME="meilisearch-sync-service"

# 获取脚本所在目录的绝对路径
WORK_DIR=$(cd "$(dirname "$0")" && pwd)
BINARY_PATH="$WORK_DIR/$BINARY_NAME"
PID_FILE="$WORK_DIR/$SERVICE_NAME.pid"
LOG_FILE="$WORK_DIR/app.log"

# 检查二进制文件是否存在
if [ ! -f "$BINARY_PATH" ]; then
    echo "错误: 找不到二进制文件 $BINARY_PATH"
    echo "请先执行 ./build.sh 进行编译"
    exit 1
fi

start() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p $PID > /dev/null 2>&1; then
            echo "$SERVICE_NAME 正在运行中 (PID: $PID)"
            return
        else
            echo "PID 文件存在但进程未运行，正在清理..."
            rm "$PID_FILE"
        fi
    fi

    echo "正在启动 $SERVICE_NAME ..."
    cd "$WORK_DIR"
    
    # 赋予执行权限
    chmod +x "$BINARY_PATH"
    
    # 后台运行并将日志重定向
    nohup "$BINARY_PATH" > "$LOG_FILE" 2>&1 &
    
    PID=$!
    echo $PID > "$PID_FILE"
    echo "$SERVICE_NAME 已启动 (PID: $PID)"
    echo "日志文件: $LOG_FILE"
}

stop() {
    if [ ! -f "$PID_FILE" ]; then
        echo "$SERVICE_NAME 未运行 (PID 文件不存在)"
        return
    fi

    PID=$(cat "$PID_FILE")
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
    
    rm -f "$PID_FILE"
}

status() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p $PID > /dev/null 2>&1; then
            echo "$SERVICE_NAME 正在运行 (PID: $PID)"
            echo "--------------------------------"
            echo "最近 10 行日志:"
            tail -n 10 "$LOG_FILE"
        else
            echo "$SERVICE_NAME 未运行 (PID 文件存在但进程丢失)"
        fi
    else
        echo "$SERVICE_NAME 未运行"
    fi
}

log() {
    if [ -f "$LOG_FILE" ]; then
        tail -f "$LOG_FILE"
    else
        echo "日志文件不存在: $LOG_FILE"
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
