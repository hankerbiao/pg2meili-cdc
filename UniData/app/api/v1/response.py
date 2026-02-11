"""统一响应封装。"""


def ok(data):
    """统一成功返回格式。"""
    return {"data": data, "message": "ok"}
