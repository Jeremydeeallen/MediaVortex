// directive: table-renderer-service | // see shared-table-renderer.S1
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { InlineEditorRegistry } from '../../static/js/TableRenderer/InlineEditors/InlineEditorRegistry.js';

/** Registered editor is retrievable by name */
test('Register then Resolve returns the same class', () => {
    const R = new InlineEditorRegistry();
    class FakeEditor {}
    R.Register('Fake', FakeEditor);
    assert.equal(R.Resolve('Fake'), FakeEditor);
});

/** Has reports membership */
test('Has reflects registration', () => {
    const R = new InlineEditorRegistry();
    class FakeEditor {}
    assert.equal(R.Has('Fake'), false);
    R.Register('Fake', FakeEditor);
    assert.equal(R.Has('Fake'), true);
});

/** Resolve throws on unknown name */
test('Resolve throws on unknown name', () => {
    const R = new InlineEditorRegistry();
    assert.throws(() => R.Resolve('Nope'));
});

/** Built-in Text and Select editors are pre-registered */
test('Built-in editors are registered out of the box', () => {
    const R = new InlineEditorRegistry();
    assert.equal(R.Has('Text'), true);
    assert.equal(R.Has('Select'), true);
});
