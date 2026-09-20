"""Saved target schemas, as the browser sees them.

The built-in template is served alongside a visitor's own schemas but is not
stored for them: it is read-only, and editing it means saving a copy. That keeps
one shipped definition rather than a seeded row per session that drifts as the
template changes.

A schema is validated on the way in by constructing a `TargetSchema`, so the
model's own rules — one identity field, no duplicate names, an enum needs values,
a date pair must reference a field that exists — are what the API enforces. There
is no second validation layer here to disagree with the first.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, File, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ValidationError

from schemabridge.api.views import target_schema_view
from schemabridge.domain.schema import MAX_FIELDS, TargetFieldSpec, TargetSchema, ValueKind
from schemabridge.domain.spec import MAX_SPEC_BYTES, SpecError, parse_spec, to_yaml
from schemabridge.domain.target import BUILTIN_SCHEMA
from schemabridge.server import schemas as store
from schemabridge.server.auth import principal_from_request
from schemabridge.server.sessions import require_same_origin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/schemas", tags=["schemas"])


class FieldInput(BaseModel):
    """One field as the builder submits it.

    Mirrors `TargetFieldSpec` rather than reusing it, so a request cannot set
    things the builder has no business setting — `aliases` in particular, which
    are derived, not supplied.
    """

    name: str
    label: str = ""
    description: str = ""
    required: bool = False
    kind: ValueKind = ValueKind.TEXT
    is_identity: bool = False
    is_unique: bool = False
    enum_values: list[str] = []
    value_aliases: dict[str, str] = {}
    not_before: str | None = None


class SpecInput(BaseModel):
    """A spec pasted rather than uploaded as a file."""

    text: str
    name: str | None = None


class SchemaInput(BaseModel):
    name: str
    description: str = ""
    fields: list[FieldInput]
    #: The version the editor last read. Required on a save so a concurrent edit
    #: cannot be silently discarded.
    if_version: int | None = None


def _build(payload: SchemaInput, schema_id: str, version: int) -> TargetSchema:
    """Turn a submission into a schema, or explain why it is not one."""
    if not payload.name.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Give the schema a name."
        )
    if len(payload.fields) > MAX_FIELDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"A schema may have at most {MAX_FIELDS} fields.",
        )
    try:
        return TargetSchema(
            schema_id=schema_id,
            name=payload.name.strip(),
            description=payload.description.strip(),
            version=version,
            builtin=False,
            fields=tuple(
                TargetFieldSpec(
                    name=field.name,
                    # A field with no label is named by its own name rather than
                    # showing blank everywhere it appears.
                    label=field.label.strip() or field.name,
                    description=field.description.strip(),
                    required=field.required,
                    kind=field.kind,
                    is_identity=field.is_identity,
                    is_unique=field.is_unique,
                    enum_values=tuple(value for v in field.enum_values if (value := v.strip())),
                    value_aliases=field.value_aliases,
                    not_before=field.not_before,
                )
                for field in payload.fields
            ),
        )
    except ValidationError as error:
        # The model's own message is the useful one: it says which field and why.
        first = error.errors()[0]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(first.get("msg", "That schema is not valid.")).removeprefix("Value error, "),
        ) from None


def _require_session(request: Request) -> str:
    """Compatibility name for the workspace id resolved from a verified token."""
    return principal_from_request(request).owner_id


def _unavailable(error: Exception) -> HTTPException:
    logger.warning("schema store unavailable: %s", type(error).__name__)
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Saved schemas are unavailable right now.",
    )


@router.get("")
def list_schemas(request: Request) -> dict[str, Any]:
    """The built-in template plus whatever the caller has saved."""
    owner_id = principal_from_request(request).owner_id
    saved: list[Any] = []
    try:
        saved = store.list_schemas(owner_id)
    except Exception as error:
        raise _unavailable(error) from None
    return {
        "builtin": target_schema_view(BUILTIN_SCHEMA),
        "schemas": [
            {
                **target_schema_view(record.schema),
                "updated_at": record.updated_at.isoformat(),
            }
            for record in saved
        ],
        "limits": {"max_fields": MAX_FIELDS, "max_schemas": store.MAX_PER_SESSION},
    }


def _read(text: str, fallback: str) -> dict[str, Any]:
    """Parse a spec into the builder's starting point.

    Deliberately does not save. The import may have had to guess which field
    identifies a record — JSON Schema cannot express that — so the result opens in
    the builder for review. Saving silently would make a guess into the contract a
    migration ran against without anybody seeing it.
    """
    try:
        imported = parse_spec(text, fallback_name=fallback)
    except SpecError as problem:
        # The parser's message is written for a person and names the line.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(problem)) from None
    return {
        **target_schema_view(imported.schema),
        # Surfaced rather than folded in, so the builder can show what it inferred
        # instead of presenting a guess as though the file had said it.
        "assumptions": list(imported.assumptions),
    }


# Two routes rather than one taking either: a single handler cannot accept both a
# multipart file and a JSON body, because the content type decides how the whole
# request is parsed. Trying to do both leaves whichever is declared second unbound.
@router.post("/import")
async def import_spec_file(
    request: Request,
    file: Annotated[UploadFile, File()],
) -> dict[str, Any]:
    """Read an uploaded JSON or YAML spec file."""
    raw = await file.read()
    if len(raw) > MAX_SPEC_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"That spec is larger than {MAX_SPEC_BYTES // 1024}KB.",
        )
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="That file is not valid UTF-8 text.",
        ) from None
    return _read(text, (file.filename or "Imported schema").rsplit(".", 1)[0])


@router.post("/import/text")
def import_spec_text(request: Request, pasted: SpecInput) -> dict[str, Any]:
    """Read a spec pasted as text."""
    if not pasted.text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Paste the spec's contents."
        )
    return _read(pasted.text, pasted.name or "Imported schema")


@router.get("/{schema_id}/spec", response_class=PlainTextResponse)
def export_spec(schema_id: str, request: Request) -> Response:
    """A schema as a YAML spec, for version control or another engagement.

    Written in this tool's own format rather than JSON Schema, which cannot
    express which field identifies a record, which must be unique, or an enum's
    accepted spellings. A round trip through JSON Schema would silently drop
    those; `parse_spec` reads this back exactly.
    """
    schema = BUILTIN_SCHEMA
    if schema_id != BUILTIN_SCHEMA.schema_id:
        session_id = _require_session(request)
        try:
            record = store.find_schema(schema_id, session_id)
        except Exception as error:
            raise _unavailable(error) from None
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such schema.")
        schema = record.schema

    filename = (
        "".join(
            character if character.isalnum() or character in "-_" else "-"
            for character in schema.name.lower()
        ).strip("-")
        or "schema"
    )
    return PlainTextResponse(
        to_yaml(schema),
        media_type="application/yaml",
        headers={"Content-Disposition": f'attachment; filename="{filename}.schema.yaml"'},
    )


@router.get("/{schema_id}")
def read_schema(schema_id: str, request: Request) -> dict[str, Any]:
    """One schema, the caller's own or the built-in template."""
    if schema_id == BUILTIN_SCHEMA.schema_id:
        return target_schema_view(BUILTIN_SCHEMA)
    session_id = _require_session(request)
    try:
        record = store.find_schema(schema_id, session_id)
    except Exception as error:
        raise _unavailable(error) from None
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such schema.")
    return {**target_schema_view(record.schema), "updated_at": record.updated_at.isoformat()}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_schema(request: Request, payload: SchemaInput) -> dict[str, Any]:
    """Save a schema in the resolved personal or shared workspace."""
    require_same_origin(request)
    session_id = _require_session(request)
    # Built with a placeholder id: the store assigns the real one, so a caller
    # cannot choose an id that collides or impersonates the built-in template.
    schema = _build(payload, schema_id="pending", version=1)
    try:
        if store.count_for_session(session_id) >= store.MAX_PER_SESSION:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"You already have {store.MAX_PER_SESSION} saved schemas.",
            )
        record = store.create_schema(session_id, schema)
    except HTTPException:
        raise
    except Exception as error:
        raise _unavailable(error) from None
    return target_schema_view(record.schema)


@router.put("/{schema_id}")
def replace_schema(schema_id: str, request: Request, payload: SchemaInput) -> dict[str, Any]:
    """Save changes to a schema the caller owns."""
    if schema_id == BUILTIN_SCHEMA.schema_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=("The built-in schema cannot be edited. Save it as a copy and edit that."),
        )
    require_same_origin(request)
    session_id = _require_session(request)
    if payload.if_version is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Saving needs the version the editor last read.",
        )
    schema = _build(payload, schema_id=schema_id, version=payload.if_version)
    try:
        record = store.update_schema(schema_id, session_id, schema, if_version=payload.if_version)
    except store.StaleWriteError as stale:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(stale)) from None
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No such schema."
        ) from None
    except HTTPException:
        raise
    except Exception as error:
        raise _unavailable(error) from None
    return {**target_schema_view(record.schema), "updated_at": record.updated_at.isoformat()}


@router.delete("/{schema_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_schema(schema_id: str, request: Request) -> Response:
    """Forget a saved schema. Runs that used it keep their own snapshot."""
    if schema_id == BUILTIN_SCHEMA.schema_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The built-in schema cannot be deleted.",
        )
    require_same_origin(request)
    session_id = _require_session(request)
    try:
        deleted = store.delete_schema(schema_id, session_id)
    except Exception as error:
        raise _unavailable(error) from None
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such schema.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
