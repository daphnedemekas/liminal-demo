# How to View Backend Logs

## Log File Location

The backend logs are written to:
```
/Users/daphnedemekas/Desktop/liminal-demo/backend.log
```

## Viewing Logs

### Option 1: View Log File (Recommended)
```bash
# View last 50 lines
tail -50 backend.log

# Follow logs in real-time (like `tail -f`)
tail -f backend.log

# View all logs
cat backend.log

# Search for specific terms
grep "ERROR" backend.log
grep "Document" backend.log
grep "WebSocket" backend.log
```

### Option 2: View in Terminal
If you started the backend manually in a terminal, logs appear there in real-time.

### Option 3: Check Running Process
The backend is currently running with uvicorn. You can see its output by:
1. Finding the process: `ps aux | grep uvicorn`
2. The logs go to stdout/stderr, which may be redirected to `backend.log`

## What You'll See in Logs

- **Database operations**: `[Database]`, `[DB]`
- **WebSocket connections**: `[WebSocket]`, `connection open/closed`
- **API requests**: HTTP status codes and endpoints
- **Orchestrator activity**: `[Orchestrator]`, `[Discovery]`, `[TeachingOrchestrator]`
- **Document/Terminal operations**: `[DocumentWS]`, `[TerminalWS]`
- **Errors**: Any exceptions or failures

## Real-Time Monitoring

To watch logs as they happen:
```bash
tail -f backend.log
```

Press `Ctrl+C` to stop following.

## Filtering Logs

```bash
# Only see errors
grep -i error backend.log

# Only see document-related logs
grep -i document backend.log

# Only see WebSocket activity
grep -i websocket backend.log

# See last 100 lines with timestamps
tail -100 backend.log | grep -E "INFO:|ERROR:|\["
```

## Log File Size

The log file can grow large over time. To clear it:
```bash
# Backup first
cp backend.log backend.log.backup

# Then clear
> backend.log
```

Or rotate logs:
```bash
# Move old log
mv backend.log backend.log.old

# Start fresh
touch backend.log
```



