#!/usr/bin/env python3
"""
DiagnoseStuckJobs.py - Enhanced Stuck Job Diagnostic Tool
Diagnoses and optionally fixes stuck transcoding and quality test jobs.
"""

import sys
import os
import argparse
from datetime import datetime
from typing import List, Dict, Any, Optional

# Add parent directory to path to import shared services
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
root_dir = os.path.dirname(parent_dir)
sys.path.append(root_dir)

from Repositories.DatabaseManager import DatabaseManager
from Services.LoggingService import LoggingService
from Services.StuckJobDetectionService import StuckJobDetectionService
from Services.ProcessManagementService import ProcessManagementService


class StuckJobDiagnostic:
    """Diagnostic tool for stuck jobs and orphaned FFmpeg processes."""
    
    def __init__(self):
        """Initialize the diagnostic tool."""
        self.DatabaseManager = DatabaseManager()
        self.DetectionService = StuckJobDetectionService(self.DatabaseManager)
        self.ProcessManagementService = ProcessManagementService()
    
    def RunFullDiagnostic(self) -> Dict[str, Any]:
        """Run comprehensive diagnostic of stuck jobs and orphaned processes."""
        try:
            LoggingService.LogInfo("Starting comprehensive stuck job diagnostic", "StuckJobDiagnostic", "RunFullDiagnostic")
            
            # Get all running FFmpeg processes
            ffmpegProcesses = self.ProcessManagementService.FindFFmpegProcesses()
            
            # Get all running jobs from database
            runningTranscodeJobs = self.DatabaseManager.GetTranscodeQueueItemsByStatus("Running")
            runningQualityJobs = self.DatabaseManager.GetQualityTestQueueItemsByStatus("Running")
            
            # Get tracked PIDs
            trackedPids = self.DatabaseManager.GetAllActiveJobProcessIds()
            
            # Run correlation analysis
            correlationResult = self.DetectionService.CorrelateFFmpegWithJobs()
            
            # Run orphaned process detection
            orphanedResult = self.DetectionService.FindOrphanedFFmpegProcesses()
            
            # Analyze results
            analysis = self.AnalyzeDiagnosticResults(
                ffmpegProcesses, 
                runningTranscodeJobs, 
                runningQualityJobs, 
                trackedPids,
                correlationResult,
                orphanedResult
            )
            
            LoggingService.LogInfo(f"Diagnostic complete: {analysis['Summary']['TotalIssues']} issues found", 
                                 "StuckJobDiagnostic", "RunFullDiagnostic")
            
            return {
                "Success": True,
                "Timestamp": datetime.now().isoformat(),
                "FFmpegProcesses": ffmpegProcesses,
                "RunningTranscodeJobs": runningTranscodeJobs,
                "RunningQualityJobs": runningQualityJobs,
                "TrackedPids": trackedPids,
                "CorrelationResult": correlationResult,
                "OrphanedResult": orphanedResult,
                "Analysis": analysis
            }
            
        except Exception as e:
            LoggingService.LogException("Error running diagnostic", e, "StuckJobDiagnostic", "RunFullDiagnostic")
            return {
                "Success": False,
                "ErrorMessage": str(e),
                "Timestamp": datetime.now().isoformat()
            }
    
    def AnalyzeDiagnosticResults(self, ffmpegProcesses: List[Dict], runningTranscodeJobs: List, 
                                runningQualityJobs: List, trackedPids: List[int],
                                correlationResult: Dict, orphanedResult: Dict) -> Dict[str, Any]:
        """Analyze diagnostic results and provide recommendations."""
        
        orphanedProcesses = orphanedResult.get("OrphanedProcesses", [])
        stuckJobs = correlationResult.get("StuckJobs", [])
        healthyJobs = correlationResult.get("HealthyJobs", [])
        
        # Categorize issues
        issues = []
        recommendations = []
        
        # Check for orphaned FFmpeg processes
        if orphanedProcesses:
            for process in orphanedProcesses:
                issues.append({
                    "Type": "OrphanedFFmpeg",
                    "Severity": "Medium",
                    "Pid": process["Pid"],
                    "Cmdline": process["Cmdline"],
                    "InputFile": process.get("InputFile"),
                    "OutputFile": process.get("OutputFile"),
                    "OperationType": process.get("OperationType"),
                    "Description": f"FFmpeg process {process['Pid']} running but not tracked in database"
                })
                recommendations.append(f"Kill orphaned FFmpeg process {process['Pid']}: {process.get('InputFile', 'Unknown input')}")
        
        # Check for stuck jobs
        if stuckJobs:
            for job in stuckJobs:
                issues.append({
                    "Type": "StuckJob",
                    "Severity": "High",
                    "JobId": job["JobId"],
                    "JobType": job["JobType"],
                    "FileName": job.get("FileName") or job.get("OriginalFilePath", "Unknown"),
                    "Reason": job["Reason"],
                    "Description": f"Job {job['JobId']} marked as Running but FFmpeg process not found"
                })
                recommendations.append(f"Reset stuck {job['JobType']} job {job['JobId']}: {job.get('FileName', 'Unknown file')}")
        
        # Check for potential PID mismatches
        for process in ffmpegProcesses:
            if process['Pid'] in trackedPids:
                # This process is tracked, check if it matches the job
                # This would require more complex correlation logic
                pass
        
        # Summary
        totalIssues = len(issues)
        criticalIssues = len([i for i in issues if i["Severity"] == "High"])
        mediumIssues = len([i for i in issues if i["Severity"] == "Medium"])
        
        return {
            "Summary": {
                "TotalIssues": totalIssues,
                "CriticalIssues": criticalIssues,
                "MediumIssues": mediumIssues,
                "OrphanedProcesses": len(orphanedProcesses),
                "StuckJobs": len(stuckJobs),
                "HealthyJobs": len(healthyJobs)
            },
            "Issues": issues,
            "Recommendations": recommendations,
            "CanAutoFix": len(orphanedProcesses) > 0 or len(stuckJobs) > 0
        }
    
    def PrintDiagnosticReport(self, DiagnosticResult: Dict[str, Any]):
        """Print a formatted diagnostic report."""
        if not DiagnosticResult.get("Success", False):
            print(f"\n❌ DIAGNOSTIC FAILED: {DiagnosticResult.get('ErrorMessage', 'Unknown error')}")
            return
        
        analysis = DiagnosticResult.get("Analysis", {})
        summary = analysis.get("Summary", {})
        issues = analysis.get("Issues", [])
        recommendations = analysis.get("Recommendations", [])
        
        print(f"\n=== STUCK JOB DIAGNOSTIC REPORT ===")
        print(f"Timestamp: {DiagnosticResult.get('Timestamp', 'Unknown')}")
        print(f"Total Issues: {summary.get('TotalIssues', 0)}")
        print(f"Critical Issues: {summary.get('CriticalIssues', 0)}")
        print(f"Medium Issues: {summary.get('MediumIssues', 0)}")
        print(f"Orphaned FFmpeg Processes: {summary.get('OrphanedProcesses', 0)}")
        print(f"Stuck Jobs: {summary.get('StuckJobs', 0)}")
        print(f"Healthy Jobs: {summary.get('HealthyJobs', 0)}")
        
        if issues:
            print(f"\n=== ISSUES FOUND ===")
            for i, issue in enumerate(issues, 1):
                severity_icon = "🔴" if issue["Severity"] == "High" else "🟡"
                print(f"\n{i}. {severity_icon} {issue['Type']} - {issue['Description']}")
                if issue.get("Pid"):
                    print(f"   PID: {issue['Pid']}")
                if issue.get("JobId"):
                    print(f"   Job ID: {issue['JobId']}")
                if issue.get("FileName"):
                    print(f"   File: {issue['FileName']}")
                if issue.get("Reason"):
                    print(f"   Reason: {issue['Reason']}")
                if issue.get("Cmdline"):
                    print(f"   Command: {issue['Cmdline'][:100]}...")
        
        if recommendations:
            print(f"\n=== RECOMMENDATIONS ===")
            for i, rec in enumerate(recommendations, 1):
                print(f"{i}. {rec}")
        
        if analysis.get("CanAutoFix", False):
            print(f"\n✅ AUTO-FIX AVAILABLE: Run with --auto-fix to resolve issues automatically")
        else:
            print(f"\n✅ NO ISSUES FOUND: System appears healthy")
    
    def AutoFixIssues(self, DiagnosticResult: Dict[str, Any]) -> Dict[str, Any]:
        """Automatically fix detected issues."""
        try:
            LoggingService.LogInfo("Starting automatic fix of stuck job issues", "StuckJobDiagnostic", "AutoFixIssues")
            
            # Run the recovery workflow
            recoveryResult = self.DetectionService.RecoverFromOrphanedState()
            
            if recoveryResult.get("Success", False):
                LoggingService.LogInfo(f"Auto-fix completed: {recoveryResult.get('Message', 'Unknown result')}", 
                                     "StuckJobDiagnostic", "AutoFixIssues")
            else:
                LoggingService.LogError(f"Auto-fix failed: {recoveryResult.get('ErrorMessage', 'Unknown error')}", 
                                      "StuckJobDiagnostic", "AutoFixIssues")
            
            return recoveryResult
            
        except Exception as e:
            LoggingService.LogException("Error during auto-fix", e, "StuckJobDiagnostic", "AutoFixIssues")
            return {
                "Success": False,
                "ErrorMessage": str(e)
            }
    
    def PrintFFmpegProcesses(self, ShowDetails: bool = True):
        """Print all running FFmpeg processes."""
        try:
            processes = self.ProcessManagementService.FindFFmpegProcesses()
            
            print(f"\n=== RUNNING FFMPEG PROCESSES ({len(processes)}) ===")
            
            if not processes:
                print("No FFmpeg processes found.")
                return
            
            for i, process in enumerate(processes, 1):
                print(f"\n{i}. PID {process['Pid']}: {process['Name']}")
                if ShowDetails and process.get('Cmdline'):
                    # Wrap long command lines
                    cmdline = process['Cmdline']
                    if len(cmdline) > 80:
                        words = cmdline.split()
                        lines = []
                        current_line = ""
                        for word in words:
                            if len(current_line + word) > 80:
                                if current_line:
                                    lines.append(current_line)
                                current_line = word
                            else:
                                current_line += (" " + word) if current_line else word
                        if current_line:
                            lines.append(current_line)
                        for line in lines:
                            print(f"   {line}")
                    else:
                        print(f"   {cmdline}")
                        
        except Exception as e:
            print(f"Error listing FFmpeg processes: {str(e)}")
    
    def PrintRunningJobs(self, ShowDetails: bool = True):
        """Print all running jobs from database."""
        try:
            transcodeJobs = self.DatabaseManager.GetTranscodeQueueItemsByStatus("Running")
            qualityJobs = self.DatabaseManager.GetQualityTestQueueItemsByStatus("Running")
            
            print(f"\n=== RUNNING JOBS ({len(transcodeJobs)} transcode, {len(qualityJobs)} quality test) ===")
            
            if transcodeJobs:
                print(f"\nTranscode Jobs ({len(transcodeJobs)}):")
                for i, job in enumerate(transcodeJobs, 1):
                    print(f"{i}. Job ID {job.Id}: {job.FileName}")
                    if ShowDetails:
                        print(f"   Path: {job.FilePath}")
                        print(f"   Status: {job.Status}")
            
            if qualityJobs:
                print(f"\nQuality Test Jobs ({len(qualityJobs)}):")
                for i, job in enumerate(qualityJobs, 1):
                    print(f"{i}. Job ID {job['Id']}: {job.get('OriginalFilePath', 'Unknown')}")
                    if ShowDetails:
                        print(f"   Status: {job.get('Status', 'Unknown')}")
            
            if not transcodeJobs and not qualityJobs:
                print("No running jobs found.")
                
        except Exception as e:
            print(f"Error listing running jobs: {str(e)}")


def main():
    """Main entry point for diagnostic script."""
    parser = argparse.ArgumentParser(description="MediaVortex Stuck Job Diagnostic Tool")
    
    parser.add_argument("--auto-fix", action="store_true", 
                       help="Automatically fix detected issues")
    parser.add_argument("--list-processes", action="store_true", 
                       help="List all running FFmpeg processes")
    parser.add_argument("--list-jobs", action="store_true", 
                       help="List all running jobs from database")
    parser.add_argument("--no-details", action="store_true", 
                       help="Hide detailed information")
    parser.add_argument("--quiet", action="store_true", 
                       help="Suppress non-essential output")
    
    args = parser.parse_args()
    
    try:
        diagnostic = StuckJobDiagnostic()
        
        if args.list_processes:
            # Just list FFmpeg processes
            diagnostic.PrintFFmpegProcesses(not args.no_details)
            return
        
        if args.list_jobs:
            # Just list running jobs
            diagnostic.PrintRunningJobs(not args.no_details)
            return
        
        # Run full diagnostic
        if not args.quiet:
            print("Running comprehensive stuck job diagnostic...")
        
        result = diagnostic.RunFullDiagnostic()
        
        if not args.quiet:
            diagnostic.PrintDiagnosticReport(result)
        
        # Auto-fix if requested
        if args.auto_fix and result.get("Success", False):
            analysis = result.get("Analysis", {})
            if analysis.get("CanAutoFix", False):
                if not args.quiet:
                    print(f"\n🔧 Running auto-fix...")
                
                fixResult = diagnostic.AutoFixIssues(result)
                
                if fixResult.get("Success", False):
                    if not args.quiet:
                        print(f"✅ Auto-fix completed: {fixResult.get('Message', 'Unknown result')}")
                else:
                    print(f"❌ Auto-fix failed: {fixResult.get('ErrorMessage', 'Unknown error')}")
            else:
                if not args.quiet:
                    print(f"ℹ️ No issues found that can be auto-fixed")
        
        # Exit with appropriate code
        if result.get("Success", False):
            analysis = result.get("Analysis", {})
            if analysis.get("Summary", {}).get("TotalIssues", 0) > 0:
                sys.exit(1)  # Issues found
            else:
                sys.exit(0)  # No issues
        else:
            sys.exit(2)  # Diagnostic failed
    
    except Exception as e:
        print(f"Error running diagnostic: {str(e)}")
        sys.exit(2)


if __name__ == "__main__":
    main()
