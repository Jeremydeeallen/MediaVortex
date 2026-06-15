import { IFilterController } from './Interfaces/IFilterController.js';
import { EventBus } from './EventBus.js';

// directive: table-renderer-service | // see shared-table-renderer.S1
export class FilterController extends IFilterController {
    // directive: table-renderer-service | // see shared-table-renderer.S1
    constructor(DataSource, Bus, Config) {
        super();
        if (!DataSource) throw new Error('FilterController requires a DataSource');
        if (!Bus) throw new Error('FilterController requires an EventBus');
        if (!Config) throw new Error('FilterController requires a Config');
        this._DataSource = DataSource;
        this._Bus = Bus;
        this._Config = Config;
        this._State = {};
        this._PendingTimer = null;
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    GetFilterState() { return { ...this._State }; }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    SetFilter(ColumnKey, Value) {
        if (!ColumnKey) return;
        if (Value === null || Value === undefined || Value === '') {
            delete this._State[ColumnKey];
        } else {
            this._State[ColumnKey] = Value;
        }
        this._ScheduleEmit();
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    Clear() {
        if (Object.keys(this._State).length === 0) return;
        this._State = {};
        this._ScheduleEmit();
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    _ScheduleEmit() {
        if (this._PendingTimer) clearTimeout(this._PendingTimer);
        const Delay = this._Config.DebounceMs;
        const Snapshot = { ...this._State };
        const Doit = () => {
            this._PendingTimer = null;
            this._Bus.Emit(EventBus.EventNames.FilterChanged, Snapshot);
        };
        if (Delay <= 0 || typeof setTimeout === 'undefined') { Doit(); return; }
        this._PendingTimer = setTimeout(Doit, Delay);
    }
}
