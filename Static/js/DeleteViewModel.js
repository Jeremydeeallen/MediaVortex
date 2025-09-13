/**
 * Delete ViewModel - Manages delete operation state and data
 * Follows MVVM architecture with PascalCase naming
 */
class DeleteViewModel {
    constructor() {
        this.DeleteType = '';
        this.DeleteId = 0;
        this.DeleteName = '';
    }
    
    InitializeDelete(Type, Id, Name) {
        this.DeleteType = Type;
        this.DeleteId = Id;
        this.DeleteName = Name;
    }
    
    GetDeleteMessage() {
        const ItemType = this.DeleteType === 'rootfolder' ? 'root folder' : 'media file';
        return `Are you sure you want to delete this ${ItemType}?<br><strong>${this.DeleteName}</strong>`;
    }
    
    GetDeleteUrl() {
        return this.DeleteType === 'rootfolder' ? `/api/RootFolders/${this.DeleteId}` : `/api/MediaFiles/${this.DeleteId}`;
    }
    
    GetRefreshFunction() {
        return this.DeleteType === 'rootfolder' ? LoadRootFolders : LoadMediaFiles;
    }
}
