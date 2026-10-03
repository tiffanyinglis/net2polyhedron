/**
 * A plain undo/redo stack, same rules as the Python apps': `push` records the state from BEFORE a
 * change and drops any redo history; `undo`/`redo` take the current state, hand back the one to
 * restore, and park the current state on the other stack. `limit` drops the oldest entry once full.
 */
export class UndoStack<T> {
  private undoItems: T[] = [];
  private redoItems: T[] = [];

  constructor(private limit = Infinity) {}

  get canUndo(): boolean {
    return this.undoItems.length > 0;
  }

  get canRedo(): boolean {
    return this.redoItems.length > 0;
  }

  push(before: T) {
    this.undoItems.push(before);
    if (this.undoItems.length > this.limit) this.undoItems.shift();
    this.redoItems.length = 0;
  }

  undo(current: T): T | undefined {
    if (!this.undoItems.length) return undefined;
    this.redoItems.push(current);
    return this.undoItems.pop();
  }

  redo(current: T): T | undefined {
    if (!this.redoItems.length) return undefined;
    this.undoItems.push(current);
    return this.redoItems.pop();
  }

  clear() {
    this.undoItems = [];
    this.redoItems = [];
  }
}
