# Quickstart: Video Queue Transcoding

## Overview
This quickstart demonstrates the video queue transcoding feature that processes videos from the TranscodeQueue table using HandBrake CLI with profile-based settings.

## Prerequisites
- MediaVortex application running
- HandBrake CLI available at `\MediaVortex\HandBrake\HandBrakeCLI.exe`
- Database with existing TranscodeQueue items
- At least one transcoding profile configured
- Temporary directory `c:\HandBrakeTemp\Source` accessible

## Step-by-Step Validation

### 1. Verify Queue Status
**Action**: Check current transcoding queue
**Expected**: Queue contains items with assigned profiles
**Validation**: 
- Navigate to Transcode Queue page
- Verify items are listed with FilePath, SizeMB, and AssignedProfile
- Confirm at least one item has status "pending"

### 2. Start Transcoding Operation
**Action**: Initiate transcoding of the largest file in queue
**Expected**: Transcoding job starts successfully
**Validation**:
- Click "Start Transcoding" button
- Verify job status changes to "processing"
- Confirm JobId is generated and displayed
- Check that file is copied to `c:\HandBrakeTemp\Source`

### 3. Monitor Progress
**Action**: Track transcoding progress
**Expected**: Progress updates in real-time
**Validation**:
- Progress percentage increases from 0% to 100%
- Status remains "processing" during operation
- No error messages appear in logs
- HandBrake CLI process is running

### 4. Verify Completion
**Action**: Confirm successful transcoding
**Expected**: File is transcoded and replaced
**Validation**:
- Status changes to "completed"
- Progress shows 100%
- Original file is deleted from source location
- Transcoded file is copied back to original folder
- File size is reduced (if compression occurred)
- Database records are updated with new file information

### 5. Check File Naming
**Action**: Verify resolution-based file naming
**Expected**: Filename reflects resolution change if applicable
**Validation**:
- If transcoded to lower resolution, filename indicates new resolution
- If same resolution, filename remains unchanged
- File extension matches output format from profile

### 6. Validate Database Updates
**Action**: Confirm database records are updated
**Expected**: All relevant tables reflect the transcoding operation
**Validation**:
- TranscodeQueue item status is "completed"
- TranscodeAttempts record shows success
- TranscodeFiles record contains final file information
- LoggingService entries document the operation

## Error Scenarios

### Transcoding Failure
**Action**: Simulate transcoding failure
**Expected**: Graceful error handling
**Validation**:
- Status changes to "failed"
- Error message is logged and displayed
- Original file remains intact
- Temporary files are cleaned up
- Database records show failure status

### File Access Issues
**Action**: Test with inaccessible source file
**Expected**: Proper error handling
**Validation**:
- Clear error message about file access
- Operation fails gracefully
- No partial file corruption
- Database state remains consistent

## Performance Validation

### Large File Processing
**Action**: Process largest file in queue
**Expected**: Efficient processing
**Validation**:
- Largest file is selected first
- Processing time is reasonable for file size
- Memory usage remains stable
- No system resource exhaustion

### Queue Prioritization
**Action**: Verify queue ordering
**Expected**: Largest files processed first
**Validation**:
- Queue is ordered by SizeMB descending
- DateAdded used as secondary sort
- Priority field is respected
- Manual reordering works correctly

## Success Criteria
- [ ] Transcoding starts successfully
- [ ] Progress tracking works accurately
- [ ] Files are processed in correct order (largest first)
- [ ] Output files are properly named and placed
- [ ] Database records are updated correctly
- [ ] Error handling works gracefully
- [ ] Performance is acceptable for large files
- [ ] All constitutional requirements are met (MVVM, PascalCase, logging, etc.)

## Troubleshooting
- Check HandBrake CLI path and permissions
- Verify temporary directory access
- Review database connection and schema
- Check file system permissions for source and destination
- Review logs for detailed error information
