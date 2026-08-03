"""API 路径参数校验。"""

from fastapi import HTTPException, Path, status


def valid_collection_name(
    collection: str = Path(..., description="集合名称，如 requirements, bugs"),
) -> str:
    if collection and collection.replace("-", "").replace("_", "").isalnum():
        return collection
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="collection 名称只能包含字母、数字、下划线和连字符",
    )
