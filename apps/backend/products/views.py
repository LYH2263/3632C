from django.core.cache import cache
from rest_framework.views import APIView

from common.permissions import require_merchant_permission
from common.response import error_response, success_response
from merchants.models import Merchant
from .models import Product
from .serializers import ProductSerializer


def _get_cache_version(merchant_key: str) -> int:
    return cache.get(f'product:version:{merchant_key}', 0)


def _bump_cache_version(merchant_key: str):
    key = f'product:version:{merchant_key}'
    cache.set(key, cache.get(key, 0) + 1)


def build_product_cache_key(merchant_id: str | None, keyword: str) -> str:
    merchant_part = merchant_id or 'all'
    keyword_part = keyword or '_'
    version = _get_cache_version(merchant_part)
    return f'product:list:{merchant_part}:{version}:{keyword_part}'


def invalidate_product_cache(merchant_id: int):
    _bump_cache_version(str(merchant_id))
    _bump_cache_version('all')


class ProductListView(APIView):
    def get(self, request):
        merchant_id = request.query_params.get('merchant_id')
        keyword = request.query_params.get('keyword', '').strip()
        cache_key = build_product_cache_key(merchant_id, keyword)

        cached = cache.get(cache_key)
        if cached is not None:
            return success_response(cached)

        queryset = Product.objects.all().order_by('id')
        if merchant_id:
            queryset = queryset.filter(merchant_id=merchant_id)
        if keyword:
            queryset = queryset.filter(name__icontains=keyword)

        serializer = ProductSerializer(queryset, many=True)
        cache.set(cache_key, serializer.data, 60)
        return success_response(serializer.data)

    def post(self, request):
        payload = request.data.copy()
        merchant_id = payload.get('merchant_id')
        if merchant_id is None:
            return error_response('merchant_id 必填', status_code=400)

        merchant = Merchant.objects.filter(id=merchant_id).first()
        if merchant is None:
            return error_response('商家不存在', status_code=404)

        permission_error = require_merchant_permission(request, merchant.id)
        if permission_error is not None:
            return permission_error

        payload['merchant'] = merchant.id
        serializer = ProductSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        invalidate_product_cache(merchant.id)

        return success_response(serializer.data, status_code=201)


class ProductDetailView(APIView):
    def get(self, request, product_id: int):
        product = Product.objects.filter(id=product_id).first()
        if product is None:
            return success_response(None)
        serializer = ProductSerializer(product)
        return success_response(serializer.data)

    def patch(self, request, product_id: int):
        product = Product.objects.filter(id=product_id).first()
        if product is None:
            return error_response('商品不存在', status_code=404)

        payload = request.data.copy()
        target_merchant_id = product.merchant_id
        if 'merchant_id' in payload:
            merchant = Merchant.objects.filter(id=payload.get('merchant_id')).first()
            if merchant is None:
                return error_response('商家不存在', status_code=404)
            if merchant.id != product.merchant_id:
                return error_response('不允许变更所属商家', status_code=400)
            payload['merchant'] = merchant.id
            target_merchant_id = merchant.id

        permission_error = require_merchant_permission(request, target_merchant_id)
        if permission_error is not None:
            return permission_error

        serializer = ProductSerializer(product, data=payload, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        invalidate_product_cache(target_merchant_id)
        return success_response(serializer.data)
