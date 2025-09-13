from typing import List, Optional
from Models.TranscodeProfileModel import TranscodeProfileModel
from Models.ProfileThresholdModel import ProfileThresholdModel
from Services.DatabaseService import DatabaseService
from Services.DebugService import DebugService


class DatabaseManager:
    """Handles business logic for data access operations."""
    
    def __init__(self, database_service: DatabaseService = None):
        self.DatabaseService = database_service or DatabaseService()
    
    # Profile Management Methods
    def GetAllProfiles(self) -> List[TranscodeProfileModel]:
        """Get all transcoding profiles."""
        query = "SELECT Id, ProfileName, Description, CreatedDate, LastModified FROM Profiles ORDER BY ProfileName"
        rows = self.DatabaseService.ExecuteQuery(query)
        
        profiles = []
        for row in rows:
            profile = TranscodeProfileModel(
                Id=row['Id'],
                ProfileName=row['ProfileName'],
                Description=row['Description'],
                CreatedDate=row['CreatedDate'],
                LastModified=row['LastModified']
            )
            profiles.append(profile)
        
        return profiles
    
    def GetProfileById(self, profile_id: int) -> Optional[TranscodeProfileModel]:
        """Get a specific profile by ID."""
        query = "SELECT Id, ProfileName, Description, CreatedDate, LastModified FROM Profiles WHERE Id = ?"
        rows = self.DatabaseService.ExecuteQuery(query, (profile_id,))
        
        if not rows:
            return None
        
        row = rows[0]
        return TranscodeProfileModel(
            Id=row['Id'],
            ProfileName=row['ProfileName'],
            Description=row['Description'],
            CreatedDate=row['CreatedDate'],
            LastModified=row['LastModified']
        )
    
    def SaveProfile(self, profile: TranscodeProfileModel) -> int:
        """Save a profile (insert or update) and return the profile ID."""
        try:
            DebugService.LogFunctionEntry("SaveProfile", profile.Id, profile.ProfileName, profile.Description)
            
            connection = self.DatabaseService.GetConnection()
            try:
                cursor = connection.cursor()
                
                if profile.Id is None:
                    # Insert new profile
                    DebugService.Log("Inserting new profile...")
                    query = """
                        INSERT INTO Profiles (ProfileName, Description, CreatedDate, LastModified)
                        VALUES (?, ?, ?, ?)
                    """
                    parameters = (profile.ProfileName, profile.Description, profile.CreatedDate, profile.LastModified)
                    DebugService.LogData("Insert parameters", parameters)
                    cursor.execute(query, parameters)
                    connection.commit()
                    profile_id = cursor.lastrowid
                    DebugService.Log("Profile inserted with ID: {}", profile_id)
                    return profile_id
                else:
                    # Update existing profile
                    DebugService.Log("Updating existing profile with ID: {}", profile.Id)
                    query = """
                        UPDATE Profiles 
                        SET ProfileName = ?, Description = ?, LastModified = ?
                        WHERE Id = ?
                    """
                    parameters = (profile.ProfileName, profile.Description, profile.LastModified, profile.Id)
                    DebugService.LogData("Update parameters", parameters)
                    cursor.execute(query, parameters)
                    connection.commit()
                    affected_rows = cursor.rowcount
                    DebugService.Log("Profile update affected {} rows", affected_rows)
                    return profile.Id
            finally:
                connection.close()
        except Exception as e:
            DebugService.LogException("Exception in SaveProfile", e)
            raise
    
    def DeleteProfile(self, profile_id: int) -> bool:
        """Delete a profile and its associated thresholds."""
        try:
            # Delete associated thresholds first
            self.DatabaseService.ExecuteNonQuery("DELETE FROM ProfileThresholds WHERE ProfileId = ?", (profile_id,))
            
            # Delete the profile
            affected_rows = self.DatabaseService.ExecuteNonQuery("DELETE FROM Profiles WHERE Id = ?", (profile_id,))
            return affected_rows > 0
        except Exception:
            return False
    
    # Profile Threshold Management Methods
    def GetThresholdsByProfileId(self, profile_id: int) -> List[ProfileThresholdModel]:
        """Get all thresholds for a specific profile."""
        query = """
            SELECT Id, ProfileId, Resolution, Under30MinMB, Under65MinMB, Over65MinMB,
                   VideoBitrateKbps, AudioBitrateKbps, FallbackVideoBitrateKbps,
                   FallbackAudioBitrateKbps, TranscodeDownTo
            FROM ProfileThresholds 
            WHERE ProfileId = ?
            ORDER BY Resolution
        """
        rows = self.DatabaseService.ExecuteQuery(query, (profile_id,))
        
        thresholds = []
        for row in rows:
            threshold = ProfileThresholdModel(
                Id=row['Id'],
                ProfileId=row['ProfileId'],
                Resolution=row['Resolution'],
                Under30MinMB=row['Under30MinMB'],
                Under65MinMB=row['Under65MinMB'],
                Over65MinMB=row['Over65MinMB'],
                VideoBitrateKbps=row['VideoBitrateKbps'],
                AudioBitrateKbps=row['AudioBitrateKbps'],
                FallbackVideoBitrateKbps=row['FallbackVideoBitrateKbps'],
                FallbackAudioBitrateKbps=row['FallbackAudioBitrateKbps'],
                TranscodeDownTo=row['TranscodeDownTo']
            )
            thresholds.append(threshold)
        
        return thresholds
    
    def SaveThreshold(self, threshold: ProfileThresholdModel) -> int:
        """Save a threshold (insert or update) and return the threshold ID."""
        try:
            DebugService.LogFunctionEntry("SaveThreshold", threshold.Id, threshold.ProfileId, threshold.Resolution)
            
            connection = self.DatabaseService.GetConnection()
            try:
                cursor = connection.cursor()
                
                if threshold.Id is None:
                    # Insert new threshold
                    DebugService.Log("Inserting new threshold...")
                    query = """
                        INSERT INTO ProfileThresholds 
                        (ProfileId, Resolution, Under30MinMB, Under65MinMB, Over65MinMB,
                         VideoBitrateKbps, AudioBitrateKbps, FallbackVideoBitrateKbps,
                         FallbackAudioBitrateKbps, TranscodeDownTo)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                    parameters = (
                        threshold.ProfileId, threshold.Resolution, threshold.Under30MinMB,
                        threshold.Under65MinMB, threshold.Over65MinMB, threshold.VideoBitrateKbps,
                        threshold.AudioBitrateKbps, threshold.FallbackVideoBitrateKbps,
                        threshold.FallbackAudioBitrateKbps, threshold.TranscodeDownTo
                    )
                    DebugService.LogData("Insert threshold parameters", parameters)
                    cursor.execute(query, parameters)
                    connection.commit()
                    threshold_id = cursor.lastrowid
                    DebugService.Log("Threshold inserted with ID: {}", threshold_id)
                    return threshold_id
                else:
                    # Update existing threshold
                    DebugService.Log("Updating existing threshold with ID: {}", threshold.Id)
                    query = """
                        UPDATE ProfileThresholds 
                        SET ProfileId = ?, Resolution = ?, Under30MinMB = ?, Under65MinMB = ?,
                            Over65MinMB = ?, VideoBitrateKbps = ?, AudioBitrateKbps = ?,
                            FallbackVideoBitrateKbps = ?, FallbackAudioBitrateKbps = ?,
                            TranscodeDownTo = ?
                        WHERE Id = ?
                    """
                    parameters = (
                        threshold.ProfileId, threshold.Resolution, threshold.Under30MinMB,
                        threshold.Under65MinMB, threshold.Over65MinMB, threshold.VideoBitrateKbps,
                        threshold.AudioBitrateKbps, threshold.FallbackVideoBitrateKbps,
                        threshold.FallbackAudioBitrateKbps, threshold.TranscodeDownTo, threshold.Id
                    )
                    DebugService.LogData("Update threshold parameters", parameters)
                    cursor.execute(query, parameters)
                    connection.commit()
                    affected_rows = cursor.rowcount
                    DebugService.Log("Threshold update affected {} rows", affected_rows)
                    return threshold.Id
            finally:
                connection.close()
        except Exception as e:
            DebugService.LogException("Exception in SaveThreshold", e)
            raise
    
    def DeleteThreshold(self, threshold_id: int) -> bool:
        """Delete a threshold."""
        affected_rows = self.DatabaseService.ExecuteNonQuery("DELETE FROM ProfileThresholds WHERE Id = ?", (threshold_id,))
        return affected_rows > 0
