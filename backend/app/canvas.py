"""Canvas reducer: pure, deterministic application of operations by shape id."""

from __future__ import annotations

from .contract import Canvas, Operation


class InvalidOperation(ValueError):
    pass


def apply_operations(canvas: Canvas, operations: list[Operation]) -> Canvas:
    """Return a new canvas with the operations applied in order.

    Raises InvalidOperation (leaving the input untouched) when an operation
    refers to an unknown id, re-adds an existing id, or lacks its shape.
    """
    shapes = {s.id: s for s in canvas.shapes}
    order = [s.id for s in canvas.shapes]

    for operation in operations:
        if operation.op == "add":
            if operation.shape is None:
                raise InvalidOperation(f"add {operation.shape_id}: missing shape")
            if operation.shape_id in shapes:
                raise InvalidOperation(f"add {operation.shape_id}: id already exists")
            if operation.shape.id != operation.shape_id:
                raise InvalidOperation(f"add {operation.shape_id}: shape id mismatch")
            shapes[operation.shape_id] = operation.shape
            order.append(operation.shape_id)
        elif operation.op == "update":
            if operation.shape is None:
                raise InvalidOperation(f"update {operation.shape_id}: missing shape")
            if operation.shape_id not in shapes:
                raise InvalidOperation(f"update {operation.shape_id}: unknown id")
            if operation.shape.id != operation.shape_id:
                raise InvalidOperation(f"update {operation.shape_id}: shape id mismatch")
            shapes[operation.shape_id] = operation.shape
        else:  # remove
            if operation.shape_id not in shapes:
                raise InvalidOperation(f"remove {operation.shape_id}: unknown id")
            del shapes[operation.shape_id]
            order.remove(operation.shape_id)

    return Canvas(shapes=[shapes[i] for i in order])
