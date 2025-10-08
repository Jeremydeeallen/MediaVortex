# MicroServiceQualityTest User Requirements

## What the User Wants

The user wants a **MicroServiceQualityTest** that provides automated video quality testing using VMAF (Video Multi-Method Assessment Fusion) to compare transcoded videos against their original sources.

## Core Features the User Needs

### 1. Automated Quality Testing
- **VMAF Analysis**: Compare transcoded videos against original files using FFmpeg's libvmaf
- **Queue Processing**: Automatically process quality test jobs from the database queue
- **Batch Processing**: Handle multiple quality tests simultaneously
- **Results Storage**: Store VMAF scores and test results in the database

### 2. Video File Management
- **Local File Processing**: Only process files on local drives (C:\, D:\, etc.)
- **Path Validation**: Verify file paths exist before processing
- **Resolution Detection**: Use ffprobe to get accurate video dimensions
- **Smart Scaling**: Only scale videos when resolutions actually differ

### 3. Worker Management
- **Configurable Workers**: Set number of concurrent workers via database settings
- **Dynamic Scaling**: Change worker count without restarting service
- **Worker Monitoring**: Track individual worker status and performance
- **Process Control**: Force kill frozen workers and FFmpeg processes

### 4. Service Reliability
- **Always Running**: Service runs continuously when process is active
- **Self-Healing**: Automatically restart failed workers
- **Error Handling**: Graceful handling of FFmpeg failures and timeouts
- **Resource Cleanup**: Proper cleanup of processes and temporary files

### 5. Process Management
- **Service Control**: Start/stop/restart service via Orchestrator
- **GUI Integration**: Control buttons in web interface
- **Deployment Support**: Easy restart for code updates
- **Health Monitoring**: Track service status and health

### 6. Configuration Management
- **Database Settings**: Read configuration from SystemSettings table
- **MaxConcurrentJobs**: Control number of simultaneous workers
- **No Complex Flags**: Simple numeric settings, no enable/disable logic
- **Runtime Changes**: Apply configuration changes without restart

## User's Desired Behavior

### 1. Service Startup
- **Automatic Start**: Service starts when process is launched
- **Configuration Load**: Read MaxConcurrentJobs from database settings
- **Worker Creation**: Create specified number of worker threads
- **Queue Monitoring**: Begin monitoring quality test queue immediately

### 2. Continuous Operation
- **Always Processing**: Workers continuously check for new quality test jobs
- **No Manual Start**: No need to manually enable/start workers
- **Automatic Scaling**: Adjust worker count based on database settings
- **Self-Managing**: Service handles its own internal state

### 3. Job Processing
- **Queue Polling**: Workers check database queue for pending jobs
- **File Validation**: Verify both original and transcoded files exist
- **FFmpeg Execution**: Run VMAF comparison using FFmpeg
- **Result Storage**: Save VMAF scores and test results to database
- **Error Handling**: Log failures and mark jobs as failed

### 4. Process Management
- **External Control**: Orchestrator can start/stop/restart service process
- **GUI Integration**: Web interface shows service status and controls
- **Deployment Support**: Easy restart for code updates
- **Health Monitoring**: Track if service process is running

### 5. Worker Control
- **PID Tracking**: Monitor worker and FFmpeg process IDs
- **Timeout Detection**: Detect when workers are stuck or frozen
- **Force Kill**: Terminate problematic processes
- **Auto-Restart**: Replace failed workers automatically

## What the User Expects

### 1. Simplicity
- **One Service**: Single QualityTestingService handles everything
- **No Complex State**: No external enable/disable flags
- **Clear Operation**: Service either runs or doesn't run
- **Easy Configuration**: Change worker count via database setting

### 2. Reliability
- **Self-Contained**: No external dependencies for operation
- **Fault Tolerant**: Handles worker failures gracefully
- **Resource Management**: Proper cleanup of processes and files
- **Error Recovery**: Automatic restart of failed components

### 3. Control
- **Process Management**: Start/stop service via Orchestrator
- **Worker Scaling**: Adjust concurrent workers via settings
- **Force Kill**: Terminate frozen processes when needed
- **Deployment**: Restart service for code updates

### 4. Monitoring
- **Status Visibility**: See service status in GUI
- **Worker Tracking**: Monitor individual worker performance
- **Error Logging**: Clear error messages and debugging info
- **Health Checks**: Know when service is healthy or failing
