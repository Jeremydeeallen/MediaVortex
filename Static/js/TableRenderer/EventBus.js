// directive: table-renderer-service | // see shared-table-renderer.S1
export class EventBus {
    // directive: table-renderer-service | // see shared-table-renderer.S1
    constructor() {
        this._Handlers = new Map();
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    Subscribe(EventName, Handler) {
        if (!EventBus.EventNames[EventName] && !this._IsKnownName(EventName)) {
            throw new Error(`Unknown event: ${EventName}`);
        }
        if (!this._Handlers.has(EventName)) {
            this._Handlers.set(EventName, new Set());
        }
        const Set_ = this._Handlers.get(EventName);
        Set_.add(Handler);
        return () => Set_.delete(Handler);
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    Emit(EventName, Payload) {
        const Set_ = this._Handlers.get(EventName);
        if (!Set_) return;
        for (const Handler of Set_) {
            try { Handler(Payload); } catch (Err) { console.error(`EventBus handler error for ${EventName}:`, Err); }
        }
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    Clear() {
        this._Handlers.clear();
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    _IsKnownName(Name) {
        return Object.values(EventBus.EventNames).includes(Name);
    }
}

EventBus.EventNames = Object.freeze({
    RowClicked: 'RowClicked',
    CellEdited: 'CellEdited',
    SortChanged: 'SortChanged',
    FilterChanged: 'FilterChanged',
    PageChanged: 'PageChanged',
    SelectionChanged: 'SelectionChanged'
});
