/**
 * Shared transcode status rendering.
 * Used by Queue.html and Status.html to display consistent status badges and job info.
 */

/**
 * Render a transcode service status badge.
 * @param {HTMLElement} Badge - The badge element to update
 * @param {string} Status - Service status from API (Running, Stopped, GracefulStop, Paused, Unknown)
 * @param {boolean} IsProcessing - Whether a job is actively being processed
 * @returns {Object} - { ShowStart, ShowStop, StopDisabled, ShowResume }
 */
function RenderTranscodeStatusBadge(Badge, Status, IsProcessing) {
    Badge.className = 'badge';
    var Result = { ShowStart: false, ShowStop: false, StopDisabled: true, ShowResume: false };

    if (IsProcessing) {
        Badge.textContent = 'Running';
        Badge.classList.add('bg-success');
        Result.ShowStop = true;
        Result.StopDisabled = false;
    } else if (Status === 'GracefulStop' || Status === 'Paused') {
        Badge.textContent = 'Stopping After Current Job';
        Badge.classList.add('bg-warning', 'text-dark');
        Result.ShowResume = true;
    } else if (Status === 'Stopped' || Status === 'Unknown') {
        Badge.textContent = 'Stopped';
        Badge.classList.add('bg-danger');
        Result.ShowStart = true;
        Result.ShowResume = true;
    } else if (Status === 'Running') {
        Badge.textContent = 'Idle';
        Badge.classList.add('bg-info');
    } else {
        Badge.textContent = Status;
        Badge.classList.add('bg-secondary');
    }

    return Result;
}

/**
 * Render current job info into designated elements.
 * @param {Object} CurrentJob - Job object from API (null if no active job)
 * @param {HTMLElement} JobInfoEl - Element to show when job is active
 * @param {HTMLElement} NoJobEl - Element to show when no job is active
 * @param {Object} [DetailEls] - Optional elements: { JobName, JobPercent, JobDetails }
 */
function RenderCurrentJobInfo(CurrentJob, JobInfoEl, NoJobEl, DetailEls) {
    if (CurrentJob) {
        if (DetailEls) {
            var FileName = CurrentJob.FilePath.split(/[/\\]/).pop();
            if (DetailEls.JobName) DetailEls.JobName.textContent = FileName;
            if (DetailEls.JobPercent) DetailEls.JobPercent.textContent = (CurrentJob.ProgressPercent || 0) + '%';
            if (DetailEls.JobDetails) {
                var Details = [];
                if (CurrentJob.CurrentPhase) Details.push(CurrentJob.CurrentPhase);
                if (CurrentJob.CurrentFPS) Details.push(CurrentJob.CurrentFPS + ' fps');
                if (CurrentJob.CurrentSpeed) Details.push(CurrentJob.CurrentSpeed);
                DetailEls.JobDetails.textContent = Details.join(' | ');
            }
        }
        if (JobInfoEl) JobInfoEl.classList.remove('d-none');
        if (NoJobEl) NoJobEl.classList.add('d-none');
    } else {
        if (JobInfoEl) JobInfoEl.classList.add('d-none');
        if (NoJobEl) NoJobEl.classList.remove('d-none');
    }
}
