# MediaVortex System Orchestration

## Overview

MediaVortex uses a microservices architecture with multiple services that need to be coordinated. This document describes the system orchestration options available for starting and managing the entire MediaVortex ecosystem.

## Architecture

### Services

1. **WebService** - Main Flask web application (port 5000)
2. **WorkerService** - Unified worker: transcoding, VMAF quality testing, and file scanning (replaces former TranscodeService + QualityTestService)

### Service Dependencies

```
WebService (Web UI)
    ↓
WorkerService (depends on WebService for API)
```

## Startup Options

### Option 1: Simple Orchestrator (Recommended)

The new simple orchestrator provides easy startup and shutdown of all services.

#### Benefits:
- **Simple Management** - Easy to understand and use
- **Cross-platform** - Works on Windows, Linux, and macOS
- **PID Tracking** - Tracks service processes for clean shutdown
- **No Database Coupling** - Independent of database state
- **Fast Startup** - Minimal overhead

#### Usage:

**Cross-platform Python (Recommended):**
```bash
# Start all services
python StartMediaVortex.py

# Stop all services
python StopMediaVortex.py

# Check service status
python StopMediaVortex.py --status
```


### Option 3: Individual Service Management

For manual control or debugging, you can start services individually.

#### Usage:

**Cross-platform Python:**
```bash
# Start WebService
cd WebService && python Main.py

# Start TranscodeService
cd TranscodeService && python Main.py

# Start QualityTestService
cd QualityTestService && python Main.py

# Stop all services
python StopAllServices.py
```

**Individual Service Scripts:**

**Windows PowerShell:**
```powershell
# Start individual services
.\StartTranscodeService.ps1
.\StartQualityTestService.ps1

# Stop individual services
.\StopTranscodeService.ps1
.\StopQualityTestService.ps1
```

**Cross-platform Python:**
```bash
# Start individual services (if you create individual scripts)
python StartTranscodeService.py
python StartQualityTestService.py
```

## Cross-Platform Support

### Windows
- Uses PowerShell scripts (legacy) or Python scripts (recommended)
- Virtual environments in `Scripts\` directories
- Process management with Windows-specific flags

### Linux
- Uses Python scripts exclusively
- Virtual environments in `bin/` directories
- Process management with Unix signals
- Supports `nohup` for background processes

## Service Management

### Health Monitoring

The simple orchestrator provides:
- **Process Management** - Starts and stops services cleanly
- **Cross-platform Support** - Works on Windows, Linux, and macOS
- **Simple Operation** - Easy to understand and maintain

### Logging

All services use the centralized LoggingService:
- **Database Storage** - All logs stored in PostgreSQL (Logs table)
- **Component Tracking** - Each log tagged with service name
- **Function Tracking** - Each log includes function name
- **Exception Handling** - Full stack traces for errors

### Configuration

Services can be configured via environment variables:
```bash
# Logging
export MEDIAVORTEX_LOG_LEVEL=INFO

# Health monitoring
export MEDIAVORTEX_HEALTH_CHECK_INTERVAL=30

# Service timeouts
export MEDIAVORTEX_SERVICE_STARTUP_TIMEOUT=60
export MEDIAVORTEX_MAX_SERVICE_RESTARTS=3
```

## Troubleshooting

### Common Issues

1. **Port Already in Use**
   - Check if services are already running
   - Use `--force` flag to restart
   - Use `StopAllServices.py` to stop all services

2. **Virtual Environment Issues**
   - Scripts automatically create virtual environments
   - Check Python installation
   - Verify pip is available

3. **Permission Issues**
   - On Linux, ensure scripts are executable: `chmod +x *.py`
   - Check file permissions for service directories

4. **Service Dependencies**
   - MediaVortex must start before other services
   - Check database connectivity
   - Verify all required files exist

### Debugging

1. **Check Service Status**
   ```bash
   # List all MediaVortex processes
   python -c "import psutil; [print(f'PID: {p.pid}, CMD: {\" \".join(p.cmdline())}') for p in psutil.process_iter() if 'python' in p.name() and any(x in ' '.join(p.cmdline()) for x in ['MediaVortex', 'TranscodeService', 'QualityCompareService'])]"
   ```

2. **Check Ports**
   ```bash
   # Check if port 5000 is in use
   netstat -tulpn | grep :5000
   ```

3. **View Logs**
   - Check database logs table
   - Check service-specific log files
   - Use `--verbose` flag for detailed output

## Best Practices

### Development
- Use `StartAllServices.py` for development
- Start services individually for debugging
- Use `--verbose` flag for detailed logging

### Production
- Use `StartMediaVortex.py` for production
- Monitor logs regularly
- Set up proper process monitoring

### Maintenance
- Stop all services before updates
- Use graceful shutdown (not force kill)
- Backup database before major changes
- Test service startup after changes

## File Structure

```
MediaVortex/
├── WebService/                        # Web interface
│   ├── App.py
│   ├── Main.py
│   └── requirements.txt
├── TranscodeService/                  # Transcoding microservice
│   ├── App.py
│   ├── Main.py
│   └── requirements.txt
├── QualityTestService/                # Quality testing microservice
│   ├── App.py
│   ├── Main.py
│   └── requirements.txt
├── StartMediaVortex.py                # Simple orchestrator startup
├── StopMediaVortex.py                 # Simple orchestrator shutdown
```

## Summary

The MediaVortex system orchestration provides a simple approach for managing the microservices architecture:

1. **Simple Orchestrator** - Recommended for all use cases
2. **Individual Service Management** - Useful for development and debugging

Choose the approach that best fits your needs, with the simple orchestrator being the recommended solution for most use cases.
