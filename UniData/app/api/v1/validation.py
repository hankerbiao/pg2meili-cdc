"""API 路径参数校验。"""

from fastapi import HTTPException, Path, status

from app.core.tenant import normalize_collection_name


def valid_collection_name(
    collection: str = Path(..., description="集合名称，如 requirements, bugs"),
) -> str:
    try:
        return normalize_collection_name(collection)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="collection 名称必须以字母或数字开头，且只能包含 ASCII 字母、数字、下划线和连字符，长度不超过 128",
        ) from exc
