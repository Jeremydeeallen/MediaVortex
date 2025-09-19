# Profile Assignment to Root Folder - Implementation Checklist

## Overview
Add functionality to assign transcoding profiles to all media files within a specific root folder. This feature allows bulk profile assignment without needing to scan files individually.

## Database Tables Involved
- **Profiles**: Source of available profiles
- **MediaFiles**: Target table to update `AssignedProfile` field
- **RootFolders**: Reference for root folder paths

## Architecture (MVVM Pattern)

### Models (Data Layer)
- ✅ **TranscodeProfileModel**: Already exists
- ✅ **MediaFileModel**: Already exists (has `AssignedProfile` field)
- ✅ **RootFolderModel**: Already exists

### Repository Layer (Data Access)
- ✅ **DatabaseManager**: Extend with `UpdateMediaFilesProfileByRootFolder()` method

### Business Services (Business Logic)
- ✅ **ProfileService**: Extend with `AssignProfileToRootFolder()` method

### ViewModels (Presentation Logic)
- ✅ **ProfileManagementViewModel**: Extend with `AssignProfileToRootFolder()` method

### Controllers (API Layer)
- ✅ **ProfileController**: Extend with `POST /api/profiles/assign-to-root-folder` endpoint

### Views (UI Layer)
- ✅ **FileScanning.html**: Add profile dropdown and apply button to Root Folders table

## Implementation Checklist

### Phase 1: Repository Layer (Data Access)
- [ ] Add `UpdateMediaFilesProfileByRootFolder(RootFolderPath: str, ProfileId: int) -> int` method to `DatabaseManager`
- [ ] Method should update all `MediaFiles` where `FilePath` starts with `RootFolderPath`
- [ ] Return count of files updated
- [ ] Add proper logging and error handling

### Phase 2: Business Service Layer
- [ ] Add `AssignProfileToRootFolder(RootFolderPath: str, ProfileId: int) -> Dict[str, Any]` method to `ProfileService`
- [ ] Validate that profile exists
- [ ] Validate that root folder path exists
- [ ] Call repository method to update files
- [ ] Return success/failure with count of files updated
- [ ] Add proper logging and error handling

### Phase 3: ViewModel Layer (Presentation Logic)
- [ ] Add `AssignProfileToRootFolder(RootFolderPath: str, ProfileId: int) -> Dict[str, Any]` method to `ProfileManagementViewModel`
- [ ] Call business service method
- [ ] Handle success/error messages
- [ ] Return formatted response for UI

### Phase 4: Controller Layer (API)
- [ ] Add `POST /api/profiles/assign-to-root-folder` endpoint to `ProfileController`
- [ ] Accept `RootFolderPath` and `ProfileId` in request body
- [ ] Validate input parameters
- [ ] Call ViewModel method
- [ ] Return JSON response with success/failure status
- [ ] Add proper error handling and logging

### Phase 5: UI Layer (View)
- [ ] Add "Profile" column header to Root Folders table in `FileScanning.html`
- [ ] Add profile dropdown to each root folder row
- [ ] Populate dropdown with available profiles from Profile API
- [ ] Add "Apply Profile" button to each row
- [ ] Implement JavaScript function to call Profile API
- [ ] Add success/error message display
- [ ] Add loading states during API calls

### Phase 6: Integration and Testing
- [ ] Test profile assignment with valid root folder and profile
- [ ] Test error handling with invalid root folder
- [ ] Test error handling with invalid profile
- [ ] Test error handling with non-existent root folder path
- [ ] Verify files are updated in database
- [ ] Verify UI updates correctly
- [ ] Test with different profile types

## File Structure (Complete Feature)

### New/Modified Files:
- `Repositories/DatabaseManager.py` - Add bulk update method
- `Services/ProfileService.py` - Add profile assignment business logic
- `ViewModels/ProfileManagementViewModel.py` - Add presentation logic
- `Controllers/ProfileController.py` - Add API endpoint
- `Templates/FileScanning.html` - Add UI controls and JavaScript

### API Endpoints:
- `POST /api/profiles/assign-to-root-folder` - Assign profile to all files in root folder

## Success Criteria
- [ ] User can select a profile from dropdown for any root folder
- [ ] User can click "Apply Profile" to assign profile to all files in that root folder
- [ ] System updates all `MediaFiles` with `FilePath` starting with the root folder path
- [ ] User receives feedback on success/failure and number of files updated
- [ ] Feature follows MVVM architecture principles
- [ ] Proper error handling and logging throughout
- [ ] Feature integrates seamlessly with existing profile management system

## Notes
- This feature leverages existing profile management infrastructure
- No new database tables required
- Maintains separation of concerns (profile management vs file scanning)
- Uses existing Profile API rather than mixing concerns in FileScanning API
