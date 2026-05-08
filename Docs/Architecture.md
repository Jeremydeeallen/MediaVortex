# MediaVortex Architecture

## System Overview
MediaVortex is a comprehensive media transcoding and management system built using the MVVM (Model-View-ViewModel) pattern with Python Flask backend and modern web frontend.

## Core Components

### Services Layer
- **SystemMonitoringService**: Monitors system resources including CPU, memory, disk usage, and temperature
- **WorkerService**: Unified worker -- handles transcoding, VMAF quality testing, and file scanning based on per-worker capability flags
- **WebService**: Provides REST API and web interface

### Models Layer
- **TranscodeFileModel**: Represents media files and their transcoding status
- **TranscodeProfileModel**: Defines transcoding parameters and settings
- **MediaFileModel**: Handles media file metadata and analysis
- **SystemResourceModel**: Manages system monitoring data

### ViewModels Layer
- **TranscodingViewModel**: Handles transcoding operations and progress
- **SystemMonitoringViewModel**: Manages system resource display and alerts
- **QualityTestingViewModel**: Controls quality analysis workflows

### Views Layer
- **Templates**: HTML templates with Bootstrap styling
- **Static Assets**: CSS, JavaScript, and media files
- **API Endpoints**: RESTful API for frontend communication

## Technology Stack

### Backend
- **Python 3.x**: Core application language
- **Flask**: Web framework and API server
- **PostgreSQL 16**: Database for configuration and job tracking (localhost:5432, psycopg2)
- **FFmpeg**: Media transcoding engine
- **psutil**: System resource monitoring

### Frontend
- **HTML5**: Markup structure
- **Bootstrap 5**: Responsive UI framework
- **JavaScript (ES6+)**: Client-side functionality
- **Chart.js**: Data visualization

### External Dependencies
- **LibreHardwareMonitor**: Advanced hardware monitoring and temperature detection
- **Core Temp**: CPU temperature monitoring (alternative)
- **HWiNFO64**: System information and monitoring (alternative)

## System Monitoring Architecture

### Temperature Monitoring Decision
**Decision**: Use LibreHardwareMonitor as the primary temperature monitoring solution.

**Rationale**:
- Provides detailed individual core temperature readings
- Creates WMI namespaces for programmatic access
- More accurate than basic WMI thermal zones
- Active development with recent Intel Gen 14 support
- Compatible with existing WMI-based monitoring infrastructure

**Implementation**:
- LibreHardwareMonitor runs as a background service
- SystemMonitoringService accesses temperature data via WMI
- Status page displays overall CPU temperature with core details on hover
- Fallback to other methods if LibreHardwareMonitor unavailable

### Temperature Display Strategy
- **Primary Display**: Show CPU Package temperature (overall CPU temp)
- **Hover Details**: Display individual core temperatures and statistics
- **Fallback Hierarchy**: LibreHardwareMonitor → OpenHardwareMonitor → WMI Thermal Zone → HWiNFO64

## Database Schema
- **TranscodeJobs**: Job queue and status tracking
- **TranscodeProfiles**: Transcoding parameter definitions
- **SystemSettings**: Application configuration
- **QualityTestResults**: VMAF and quality analysis data

## API Design
- **RESTful endpoints** for all operations
- **JSON responses** with consistent error handling
- **Real-time updates** via polling for status changes
- **Resource-based URLs** following REST conventions

## Security Considerations
- **Input validation** for all user inputs
- **SQL injection prevention** using parameterized queries
- **File system access controls** for media file operations
- **Process isolation** for transcoding operations

## Performance Optimization
- **Asynchronous processing** for long-running operations
- **Resource monitoring** to prevent system overload
- **Queue management** for transcoding jobs
- **Caching strategies** for frequently accessed data

## Deployment Architecture
- **Microservices**: Two services (WebService, WorkerService)
- **Local PostgreSQL**: Database runs locally (not Docker)
- **Configuration management**: Environment-based settings
- **Logging**: Comprehensive logging across all services via centralized LoggingService

## Future Enhancements
- **GPU acceleration** support for transcoding
- **Distributed processing** across multiple nodes
- **Advanced quality metrics** beyond VMAF
- **Real-time monitoring dashboard** with WebSocket updates