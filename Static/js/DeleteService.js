/**
 * Delete Service - Handles delete business logic
 * Follows MVVM architecture with PascalCase naming
 */
class DeleteService {
    constructor(DeleteViewModelInstance) {
        this.DeleteViewModel = DeleteViewModelInstance;
    }
    
    ShowDeleteConfirmation(Type, Id, Name) {
        this.DeleteViewModel.InitializeDelete(Type, Id, Name);
        const Message = this.DeleteViewModel.GetDeleteMessage();
        $('#DeleteMessage').html(Message);
        $('#DeleteModal').modal('show');
    }
    
    ExecuteDelete() {
        const Url = this.DeleteViewModel.GetDeleteUrl();
        const RefreshFunction = this.DeleteViewModel.GetRefreshFunction();
        
        $.ajax({
            url: Url,
            method: 'DELETE',
            success: (response) => {
                $('#DeleteModal').modal('hide');
                if (response.Success) {
                    ShowSuccess(response.Message || 'Item deleted successfully');
                    RefreshFunction();
                } else {
                    ShowError(response.Message || 'Failed to delete item');
                }
            },
            error: (xhr) => {
                const response = xhr.responseJSON;
                ShowError(response?.Message || 'Error deleting item');
            }
        });
    }
}
