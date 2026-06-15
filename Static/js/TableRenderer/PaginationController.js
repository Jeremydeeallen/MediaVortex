import { IPaginationController } from './Interfaces/IPaginationController.js';
import { EventBus } from './EventBus.js';

// directive: table-renderer-service | // see shared-table-renderer.S1
export class PaginationController extends IPaginationController {
    // directive: table-renderer-service | // see shared-table-renderer.S1
    constructor(DataSource, Bus, Config) {
        super();
        if (!DataSource) throw new Error('PaginationController requires a DataSource');
        if (!Bus) throw new Error('PaginationController requires an EventBus');
        if (!Config) throw new Error('PaginationController requires a Config');
        this._DataSource = DataSource;
        this._Bus = Bus;
        this._Config = Config;
        this._Page = 0;
        this._PageSize = Config.DefaultPageSize;
        this._TotalCount = 0;
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    GetPage() { return this._Page; }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    GetPageSize() { return this._PageSize; }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    SetPageSize(Size) {
        if (typeof Size !== 'number' || Size <= 0) return;
        this._PageSize = Size;
        this._Page = 0;
        this._EmitChange();
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    SetTotalCount(Total) {
        this._TotalCount = Math.max(0, Number(Total) || 0);
        const LastPage = this._LastPage();
        if (this._Page > LastPage) {
            this._Page = LastPage;
            this._EmitChange();
        }
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    NextPage() {
        const Last = this._LastPage();
        if (this._Page >= Last) return;
        this._Page += 1;
        this._EmitChange();
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    PrevPage() {
        if (this._Page <= 0) return;
        this._Page -= 1;
        this._EmitChange();
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    GoTo(Page) {
        const Next = Math.max(0, Math.min(this._LastPage(), Math.floor(Number(Page) || 0)));
        if (Next === this._Page) return;
        this._Page = Next;
        this._EmitChange();
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    _LastPage() {
        if (this._PageSize <= 0 || this._TotalCount <= 0) return 0;
        return Math.max(0, Math.ceil(this._TotalCount / this._PageSize) - 1);
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    _EmitChange() {
        this._Bus.Emit(EventBus.EventNames.PageChanged, {
            Page: this._Page,
            PageSize: this._PageSize,
            TotalCount: this._TotalCount,
            LastPage: this._LastPage()
        });
    }
}
