# MediaVortex System Orchestration

## Overview

MediaVortex uses a microservices architecture with multiple services that need to be coordinated. This document describes the system orchestration options available for starting and managing the entire MediaVortex ecosystem.

## Architecture

### Services

1. **MediaVortex** - Main Flask web application (port 5000)
2. **TranscodeService** - Microservice for transcoding operations
3. **QualityCompareService** - Microservice for quality testing operations
4. **SystemOrchestratorService** - Master controller for all services (optional)

### Service Dependencies

```
MediaVortex (Web UI)
    ↓
TranscodeService (depends on MediaVortex)
    ↓
QualityCompareService (depends on MediaVortex)
```

## Startup Options

### Option 1: SystemOrchestratorService (Recommended)

The SystemOrchestratorService acts as a master controller that manages all other services.

#### Benefits:
- **Centralized Management** - Single point of control
- **Health Monitoring** - Continuous monitoring and auto-restart
- **Dependency Management** - Ensures services start in correct order
- **Unified Logging** - Centralized logging for entire system
- **Graceful Shutdown** - Coordinated shutdown of all services

#### Usage:

**Cross-platform Python (Recommended):**
```bash
# Start all services with orchestrator
python StartSystemOrchestrator.py

# Start in background
python StartSystemOrchestrator.py --background

# Force restart if already running
python StartSystemOrchestrator.py --force

# Stop all services
python StopSystemOrchestrator.py
```

**Windows PowerShell (Legacy):**
```powershell
# Start orchestrator
.\StartSystemOrchestrator.ps1

# Start in background
.\StartSystemOrchestrator.ps1 -Background

# Stop orchestrator
.\StopSystemOrchestrator.ps1
```

### Option 2: Individual Service Management

For manual control or debugging, you can start services individually.

#### Usage:

**Cross-platform Python:**
```bash
# Start all services individually
python StartAllServices.py

# Start only MediaVortex
python StartAllServices.py --mediavortex-only

# Start only TranscodeService
python StartAllServices.py --transcode-only

# Start only QualityCompareService
python StartAllServices.py --quality-only

# Start in background
python StartAllServices.py --background

# Stop all services
python StopAllServices.py
```

**Individual Service Scripts:**

**Windows PowerShell:**
```powershell
# Start individual services
.\StartTranscodeService.ps1
.\StartQualityCompareService.ps1

# Stop individual services
.\StopTranscodeService.ps1
.\StopQualityCompareService.ps1
```

**Cross-platform Python:**
```bash
# Start individual services (if you create individual scripts)
python StartTranscodeService.py
python StartQualityCompareService.py
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

The SystemOrchestratorService provides:
- **Port Health Checks** - Verifies services are responding on their ports
- **Process Monitoring** - Ensures processes are still running
- **Auto-Restart** - Automatically restarts failed services
- **Dependency Checking** - Ensures dependent services are running

### Logging

All services use the centralized LoggingService:
- **Database Storage** - All logs stored in MediaVortex.db
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
- Use `SystemOrchestratorService` for production
- Start with `--background` flag
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
├── SystemOrchestratorService/          # Master controller
│   ├── App.py                         # Orchestrator application
│   ├── Main.py                        # Entry point
│   ├── Config.py                      # Configuration
│   └── requirements.txt               # Dependencies
├── TranscodeService/                  # Transcoding microservice
│   ├── App.py
│   ├── Main.py
│   └── requirements.txt
├── QualityCompareService/             # Quality testing microservice
│   ├── App.py
│   ├── Main.py
│   └── requirements.txt
├── StartSystemOrchestrator.py         # Cross-platform startup
├── StopSystemOrchestrator.py          # Cross-platform shutdown
├── StartAllServices.py                # Individual service startup
├── StopAllServices.py                 # Individual service shutdown
├── StartSystemOrchestrator.ps1         # Windows PowerShell (legacy)
├── StopSystemOrchestrator.ps1         # Windows PowerShell (legacy)
├── StartTranscodeService.ps1          # Windows PowerShell (legacy)
├── StopTranscodeService.ps1           # Windows PowerShell (legacy)
├── StartQualityCompareService.ps1     # Windows PowerShell (legacy)
└── StopQualityCompareService.ps1     # Windows PowerShell (legacy)
```

## Summary

The MediaVortex system orchestration provides multiple options for managing the microservices architecture:

1. **SystemOrchestratorService** - Recommended for production use
2. **Individual Service Management** - Useful for development and debugging
3. **Cross-platform Python Scripts** - Works on both Windows and Linux
4. **Legacy PowerShell Scripts** - Windows-only, maintained for compatibility

Choose the approach that best fits your needs, with SystemOrchestratorService being the recommended solution for most use cases.
