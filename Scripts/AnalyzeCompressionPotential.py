"""
Analyze compression potential in the MediaVortex database.
This script provides comprehensive analysis of files with the best compression potential.
"""

import os
import sys
import json
from pathlib import Path
from typing import Dict, List, Any, Optional

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from Repositories.DatabaseManager import DatabaseManager
from Services.LoggingService import LoggingService


class CompressionPotentialAnalyzer:
    """Analyzes compression potential of media files in the database."""
    
    def __init__(self):
        """Initialize the analyzer."""
        self.DbManager = DatabaseManager()
        self.Results = []
        
    def AnalyzeCompressionPotential(self) -> List[Dict[str, Any]]:
        """Analyze compression potential for all eligible files."""
        try:
            LoggingService.LogInfo("Starting compression potential analysis...", "AnalyzeCompressionPotential", "CompressionPotentialAnalyzer")
            
            # Read the SQL query from file
            sql_file = Path(__file__).parent / "CompressionPotentialAnalysis.sql"
            if not sql_file.exists():
                LoggingService.LogError("SQL file not found: CompressionPotentialAnalysis.sql", "AnalyzeCompressionPotential", "CompressionPotentialAnalyzer")
                return []
            
            with open(sql_file, 'r', encoding='utf-8') as f:
                query = f.read()
            
            # Execute the query
            results = self.DbManager.DatabaseService.ExecuteQuery(query)
            
            if not results:
                LoggingService.LogWarning("No files found for compression analysis", "AnalyzeCompressionPotential", "CompressionPotentialAnalyzer")
                return []
            
            LoggingService.LogInfo(f"Found {len(results)} files with compression potential", "AnalyzeCompressionPotential", "CompressionPotentialAnalyzer")
            
            # Process and enhance results
            processed_results = self.ProcessResults(results)
            
            # Generate summary statistics
            summary = self.GenerateSummary(processed_results)
            
            # Log summary
            self.LogSummary(summary)
            
            return processed_results
            
        except Exception as e:
            LoggingService.LogException("Error analyzing compression potential", e, "AnalyzeCompressionPotential", "CompressionPotentialAnalyzer")
            return []
    
    def ProcessResults(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Process and enhance the query results."""
        try:
            processed = []
            
            for row in results:
                # Add calculated fields
                processed_row = dict(row)
                
                # Calculate total potential savings
                total_savings_gb = (row.get('EstimatedSpaceSavingsMB', 0) or 0) / 1024
                processed_row['EstimatedSpaceSavingsGB'] = round(total_savings_gb, 2)
                
                # Add compression efficiency rating
                compression_score = row.get('CompressionScore', 0) or 0
                if compression_score >= 80:
                    efficiency_rating = "Excellent"
                elif compression_score >= 60:
                    efficiency_rating = "Good"
                elif compression_score >= 40:
                    efficiency_rating = "Fair"
                elif compression_score >= 20:
                    efficiency_rating = "Poor"
                else:
                    efficiency_rating = "Very Poor"
                
                processed_row['EfficiencyRating'] = efficiency_rating
                
                # Add recommended action
                if row.get('ProcessingStatus') == 'Not Processed':
                    if compression_score >= 60:
                        recommended_action = "High Priority - Transcode Immediately"
                    elif compression_score >= 40:
                        recommended_action = "Medium Priority - Schedule for Transcoding"
                    elif compression_score >= 20:
                        recommended_action = "Low Priority - Consider Transcoding"
                    else:
                        recommended_action = "Very Low Priority - Skip or Manual Review"
                else:
                    recommended_action = "Already Processed or Assigned"
                
                processed_row['RecommendedAction'] = recommended_action
                
                processed.append(processed_row)
            
            return processed
            
        except Exception as e:
            LoggingService.LogException("Error processing results", e, "ProcessResults", "CompressionPotentialAnalyzer")
            return []
    
    def GenerateSummary(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate summary statistics from the results."""
        try:
            if not results:
                return {}
            
            # Basic counts
            total_files = len(results)
            total_size_mb = sum(row.get('SizeMB', 0) or 0 for row in results)
            total_potential_savings_mb = sum(row.get('EstimatedSpaceSavingsMB', 0) or 0 for row in results)
            
            # Codec distribution
            codec_counts = {}
            for row in results:
                codec = row.get('Codec', 'Unknown')
                codec_counts[codec] = codec_counts.get(codec, 0) + 1
            
            # Resolution distribution
            resolution_counts = {}
            for row in results:
                resolution = row.get('Resolution', 'Unknown')
                resolution_counts[resolution] = resolution_counts.get(resolution, 0) + 1
            
            # Efficiency rating distribution
            efficiency_counts = {}
            for row in results:
                rating = row.get('EfficiencyRating', 'Unknown')
                efficiency_counts[rating] = efficiency_counts.get(rating, 0) + 1
            
            # Priority distribution
            priority_counts = {}
            for row in results:
                action = row.get('RecommendedAction', 'Unknown')
                priority_counts[action] = priority_counts.get(action, 0) + 1
            
            summary = {
                'TotalFiles': total_files,
                'TotalSizeMB': round(total_size_mb, 2),
                'TotalSizeGB': round(total_size_mb / 1024, 2),
                'TotalPotentialSavingsMB': round(total_potential_savings_mb, 2),
                'TotalPotentialSavingsGB': round(total_potential_savings_mb / 1024, 2),
                'AverageSavingsPercent': round((total_potential_savings_mb / total_size_mb * 100) if total_size_mb > 0 else 0, 1),
                'CodecDistribution': codec_counts,
                'ResolutionDistribution': resolution_counts,
                'EfficiencyDistribution': efficiency_counts,
                'PriorityDistribution': priority_counts
            }
            
            return summary
            
        except Exception as e:
            LoggingService.LogException("Error generating summary", e, "GenerateSummary", "CompressionPotentialAnalyzer")
            return {}
    
    def LogSummary(self, summary: Dict[str, Any]) -> None:
        """Log the summary statistics."""
        try:
            if not summary:
                return
            
            LoggingService.LogInfo("=== COMPRESSION POTENTIAL ANALYSIS SUMMARY ===", "LogSummary", "CompressionPotentialAnalyzer")
            LoggingService.LogInfo(f"Total Files Analyzed: {summary.get('TotalFiles', 0)}", "LogSummary", "CompressionPotentialAnalyzer")
            LoggingService.LogInfo(f"Total Size: {summary.get('TotalSizeGB', 0):.2f} GB", "LogSummary", "CompressionPotentialAnalyzer")
            LoggingService.LogInfo(f"Potential Savings: {summary.get('TotalPotentialSavingsGB', 0):.2f} GB", "LogSummary", "CompressionPotentialAnalyzer")
            LoggingService.LogInfo(f"Average Savings: {summary.get('AverageSavingsPercent', 0):.1f}%", "LogSummary", "CompressionPotentialAnalyzer")
            
            # Log codec distribution
            LoggingService.LogInfo("Codec Distribution:", "LogSummary", "CompressionPotentialAnalyzer")
            for codec, count in summary.get('CodecDistribution', {}).items():
                LoggingService.LogInfo(f"  {codec}: {count} files", "LogSummary", "CompressionPotentialAnalyzer")
            
            # Log efficiency distribution
            LoggingService.LogInfo("Efficiency Distribution:", "LogSummary", "CompressionPotentialAnalyzer")
            for rating, count in summary.get('EfficiencyDistribution', {}).items():
                LoggingService.LogInfo(f"  {rating}: {count} files", "LogSummary", "CompressionPotentialAnalyzer")
            
            # Log priority distribution
            LoggingService.LogInfo("Priority Distribution:", "LogSummary", "CompressionPotentialAnalyzer")
            for action, count in summary.get('PriorityDistribution', {}).items():
                LoggingService.LogInfo(f"  {action}: {count} files", "LogSummary", "CompressionPotentialAnalyzer")
            
        except Exception as e:
            LoggingService.LogException("Error logging summary", e, "LogSummary", "CompressionPotentialAnalyzer")
    
    def ExportResults(self, results: List[Dict[str, Any]], filename: Optional[str] = None) -> str:
        """Export results to JSON file."""
        try:
            if not filename:
                filename = f"CompressionPotentialAnalysis_{Path(__file__).stem}.json"
            
            output_path = Path(__file__).parent / filename
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, default=str)
            
            LoggingService.LogInfo(f"Results exported to: {output_path}", "ExportResults", "CompressionPotentialAnalyzer")
            return str(output_path)
            
        except Exception as e:
            LoggingService.LogException("Error exporting results", e, "ExportResults", "CompressionPotentialAnalyzer")
            return ""
    
    def GetTopCompressionCandidates(self, results: List[Dict[str, Any]], limit: int = 10) -> List[Dict[str, Any]]:
        """Get the top compression candidates."""
        try:
            # Sort by priority score and compression score
            sorted_results = sorted(
                results, 
                key=lambda x: (x.get('PriorityScore', 0), x.get('CompressionScore', 0)), 
                reverse=True
            )
            
            return sorted_results[:limit]
            
        except Exception as e:
            LoggingService.LogException("Error getting top candidates", e, "GetTopCompressionCandidates", "CompressionPotentialAnalyzer")
            return []


def main():
    """Main execution function."""
    try:
        LoggingService.LogInfo("Starting Compression Potential Analysis", "main", "AnalyzeCompressionPotential")
        
        analyzer = CompressionPotentialAnalyzer()
        
        # Analyze compression potential
        results = analyzer.AnalyzeCompressionPotential()
        
        if not results:
            LoggingService.LogWarning("No results found for analysis", "main", "AnalyzeCompressionPotential")
            return
        
        # Export results
        export_path = analyzer.ExportResults(results)
        
        # Get top candidates
        top_candidates = analyzer.GetTopCompressionCandidates(results, 10)
        
        LoggingService.LogInfo("=== TOP 10 COMPRESSION CANDIDATES ===", "main", "AnalyzeCompressionPotential")
        for i, candidate in enumerate(top_candidates, 1):
            LoggingService.LogInfo(
                f"{i}. {candidate.get('FileName', 'Unknown')} - "
                f"Score: {candidate.get('CompressionScore', 0)} - "
                f"Savings: {candidate.get('EstimatedSpaceSavingsMB', 0):.1f}MB - "
                f"Action: {candidate.get('RecommendedAction', 'Unknown')}",
                "main", "AnalyzeCompressionPotential"
            )
        
        LoggingService.LogInfo(f"Analysis complete. Results exported to: {export_path}", "main", "AnalyzeCompressionPotential")
        
    except Exception as e:
        LoggingService.LogException("Error in main execution", e, "main", "AnalyzeCompressionPotential")


if __name__ == "__main__":
    main()


