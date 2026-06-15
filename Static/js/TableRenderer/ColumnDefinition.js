// directive: table-renderer-service | // see shared-table-renderer.S1
export class ColumnDefinition {
    // directive: table-renderer-service | // see shared-table-renderer.S1
    constructor(Spec) {
        if (!Spec || !Spec.Key) throw new Error('ColumnDefinition requires Key');
        this.Key = Spec.Key;
        this.Header = Spec.Header ?? Spec.Key;
        this.Sortable = Spec.Sortable === true;
        this.Filterable = Spec.Filterable === true;
        this.Editable = Spec.Editable === true;
        this.CellRendererName = Spec.CellRendererName ?? 'Text';
        this.CellRendererOptions = Spec.CellRendererOptions ?? {};
        this.EditorName = Spec.EditorName ?? null;
        this.EditorOptions = Spec.EditorOptions ?? {};
        this.Width = Spec.Width ?? null;
        this.HeaderClass = Spec.HeaderClass ?? '';
        this.CellClass = Spec.CellClass ?? '';
        this.Align = Spec.Align ?? 'left';
    }
}
