from common.auth import get_request_user
from common.response import error_response


def check_merchant_permission(user, merchant_id: int, forbidden_message: str = '无权操作该商家数据') -> tuple[str, int] | None:
    if user is None:
        return ('请先登录', 403)
    if user.role != 'merchant':
        return ('仅商家可操作', 403)
    if user.merchant_id != merchant_id:
        return (forbidden_message, 403)
    return None


def require_merchant_permission(request, merchant_id: int, forbidden_message: str = '无权操作该商家数据'):
    user = get_request_user(request)
    error = check_merchant_permission(user, merchant_id, forbidden_message)
    if error is not None:
        return error_response(error[0], status_code=error[1])
    return None


def merchant_required(*, merchant_id_kwarg='merchant_id', forbidden_message='无权操作该商家数据'):
    def decorator(view_func):
        def wrapped(self, request, *args, **kwargs):
            merchant_id = kwargs.get(merchant_id_kwarg)
            if merchant_id is None:
                return error_response('merchant_id 缺失', status_code=400)
            permission_error = require_merchant_permission(request, merchant_id, forbidden_message)
            if permission_error is not None:
                return permission_error
            return view_func(self, request, *args, **kwargs)
        return wrapped
    return decorator
