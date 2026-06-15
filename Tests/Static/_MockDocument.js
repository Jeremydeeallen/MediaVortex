// directive: table-renderer-service | // see shared-table-renderer.S1
export class MockElement {
    // directive: table-renderer-service | // see shared-table-renderer.S1
    constructor(TagName = 'div') {
        this.tagName = TagName.toUpperCase();
        this.children = [];
        this.parentNode = null;
        this.attributes = {};
        this.style = {};
        this.classList = new MockClassList();
        this.dataset = {};
        this._InnerHTML = '';
        this.textContent = '';
        this.value = '';
        this._Listeners = new Map();
        this.scrollTop = 0;
        this.clientHeight = 0;
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    get innerHTML() { return this._InnerHTML; }
    // directive: table-renderer-service | // see shared-table-renderer.S1
    set innerHTML(V) {
        this._InnerHTML = String(V);
        if (V === '' || V === null || V === undefined) {
            for (const C of this.children) C.parentNode = null;
            this.children = [];
        }
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    appendChild(Child) {
        if (Child && Child.tagName === '#DOCUMENT-FRAGMENT') {
            for (const Grand of Child.children.slice()) {
                Grand.parentNode = this;
                this.children.push(Grand);
            }
            Child.children = [];
            return Child;
        }
        Child.parentNode = this;
        this.children.push(Child);
        return Child;
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    removeChild(Child) {
        const Idx = this.children.indexOf(Child);
        if (Idx >= 0) this.children.splice(Idx, 1);
        Child.parentNode = null;
        return Child;
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    setAttribute(Name, Value) { this.attributes[Name] = String(Value); }
    // directive: table-renderer-service | // see shared-table-renderer.S1
    getAttribute(Name) { return Object.prototype.hasOwnProperty.call(this.attributes, Name) ? this.attributes[Name] : null; }
    // directive: table-renderer-service | // see shared-table-renderer.S1
    removeAttribute(Name) { delete this.attributes[Name]; }
    // directive: table-renderer-service | // see shared-table-renderer.S1
    addEventListener(Name, Handler) {
        if (!this._Listeners.has(Name)) this._Listeners.set(Name, new Set());
        this._Listeners.get(Name).add(Handler);
    }
    // directive: table-renderer-service | // see shared-table-renderer.S1
    removeEventListener(Name, Handler) {
        const Set_ = this._Listeners.get(Name);
        if (Set_) Set_.delete(Handler);
    }
    // directive: table-renderer-service | // see shared-table-renderer.S1
    dispatchEvent(Event) {
        const Set_ = this._Listeners.get(Event.type);
        if (!Set_) return;
        for (const Handler of Set_) Handler(Event);
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    querySelectorAll(Selector) {
        const Out = [];
        const Match = (El) => {
            if (Selector.startsWith('.')) {
                if (El.classList.contains(Selector.slice(1))) Out.push(El);
            } else if (Selector.startsWith('#')) {
                if (El.attributes.id === Selector.slice(1)) Out.push(El);
            } else {
                if (El.tagName === Selector.toUpperCase()) Out.push(El);
            }
        };
        const Walk = (El) => {
            for (const C of El.children) { Match(C); Walk(C); }
        };
        Walk(this);
        return Out;
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    querySelector(Selector) {
        const All = this.querySelectorAll(Selector);
        return All.length ? All[0] : null;
    }
}

// directive: table-renderer-service | // see shared-table-renderer.S1
class MockClassList {
    // directive: table-renderer-service | // see shared-table-renderer.S1
    constructor() { this._Set = new Set(); }
    // directive: table-renderer-service | // see shared-table-renderer.S1
    add(...Names) { for (const N of Names) this._Set.add(N); }
    // directive: table-renderer-service | // see shared-table-renderer.S1
    remove(...Names) { for (const N of Names) this._Set.delete(N); }
    // directive: table-renderer-service | // see shared-table-renderer.S1
    contains(Name) { return this._Set.has(Name); }
    // directive: table-renderer-service | // see shared-table-renderer.S1
    toggle(Name) {
        if (this._Set.has(Name)) { this._Set.delete(Name); return false; }
        this._Set.add(Name); return true;
    }
}

// directive: table-renderer-service | // see shared-table-renderer.S1
export class MockDocumentFragment extends MockElement {
    // directive: table-renderer-service | // see shared-table-renderer.S1
    constructor() { super('#document-fragment'); }
}

// directive: table-renderer-service | // see shared-table-renderer.S1
export class MockDocument {
    // directive: table-renderer-service | // see shared-table-renderer.S1
    constructor() { this.body = new MockElement('body'); }
    // directive: table-renderer-service | // see shared-table-renderer.S1
    createElement(Tag) { return new MockElement(Tag); }
    // directive: table-renderer-service | // see shared-table-renderer.S1
    createDocumentFragment() { return new MockDocumentFragment(); }
    // directive: table-renderer-service | // see shared-table-renderer.S1
    querySelectorAll(Selector) { return this.body.querySelectorAll(Selector); }
    // directive: table-renderer-service | // see shared-table-renderer.S1
    querySelector(Selector) { return this.body.querySelector(Selector); }
}

// directive: table-renderer-service | // see shared-table-renderer.S1
export function InstallGlobalDocument() {
    const Doc = new MockDocument();
    globalThis.document = Doc;
    return Doc;
}
