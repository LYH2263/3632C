import threading
from unittest import skipIf

from django.db import connection
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient

from merchants.models import Merchant
from products.models import Product
from users.models import StoreUser
from .models import Order


class OrderApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.merchant = Merchant.objects.create(
            name='鲜果超市',
            phone='020-11110001',
            address='幸福社区 1 号楼底商',
            delivery_note='2 公里内 30 分钟配送',
            min_order_amount=20,
            delivery_fee=3,
            is_open=True
        )

        self.buyer = StoreUser.objects.create(
            username='buyer',
            password='buyer123',
            role='buyer',
            nickname='社区住户',
            phone='13800138000'
        )

        self.merchant_user = StoreUser.objects.create(
            username='merchant_fruit',
            password='merchant123',
            role='merchant',
            nickname='店主',
            phone='13900001111',
            merchant=self.merchant
        )

        self.product = Product.objects.create(
            merchant=self.merchant,
            name='苹果',
            price=10,
            unit='斤',
            stock=10,
            is_active=True,
            image_url='https://dummyimage.com/240x240/ffe4b5/333333&text=苹果',
            description='测试商品'
        )

    def test_login_success(self):
        response = self.client.post(
            '/api/v1/auth/login',
            {'username': 'buyer', 'password': 'buyer123'},
            format='json'
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['data']['user']['role'], 'buyer')

    def test_create_order_success(self):
        response = self.client.post(
            '/api/v1/orders',
            {
                'buyer_id': self.buyer.id,
                'merchant_id': self.merchant.id,
                'receiver_name': '测试用户',
                'receiver_phone': '13800138000',
                'receiver_address': '幸福社区 8 栋',
                'remark': '请尽快配送',
                'cart_items': [
                    {
                        'product_id': self.product.id,
                        'quantity': 2
                    }
                ]
            },
            format='json'
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['data']['status'], 'pending')
        self.assertEqual(response.data['data']['pay_method'], 'offline')
        self.assertEqual(len(response.data['data']['items_snapshot']), 1)

    def test_create_order_invalid_quantity(self):
        response = self.client.post(
            '/api/v1/orders',
            {
                'buyer_id': self.buyer.id,
                'merchant_id': self.merchant.id,
                'receiver_name': '测试用户',
                'receiver_phone': '13800138000',
                'receiver_address': '幸福社区 8 栋',
                'cart_items': [
                    {
                        'product_id': self.product.id,
                        'quantity': 0
                    }
                ]
            },
            format='json'
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Order.objects.count(), 0)

    def test_status_transition(self):
        order = Order.objects.create(
            buyer=self.buyer,
            merchant=self.merchant,
            order_no='CS202501010000000001',
            status='pending',
            pay_method='offline',
            receiver_name='测试用户',
            receiver_phone='13800138000',
            receiver_address='幸福社区 8 栋',
            items_amount=20,
            delivery_fee=3,
            total_amount=23,
            items_snapshot=[
                {
                    'product_id': self.product.id,
                    'name': '苹果',
                    'unit': '斤',
                    'price': 10,
                    'quantity': 2,
                    'subtotal': 20
                }
            ]
        )

        response = self.client.patch(
            f'/api/v1/orders/{order.id}/status',
            {'status': 'confirmed'},
            format='json',
            HTTP_AUTHORIZATION=f'Bearer django-token-{self.merchant_user.id}'
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['data']['status'], 'confirmed')

        response = self.client.patch(
            f'/api/v1/orders/{order.id}/status',
            {'status': 'completed'},
            format='json',
            HTTP_AUTHORIZATION=f'Bearer django-token-{self.merchant_user.id}'
        )
        self.assertEqual(response.status_code, 400)

    def test_status_transition_forbidden_for_non_merchant(self):
        order = Order.objects.create(
            buyer=self.buyer,
            merchant=self.merchant,
            order_no='CS202501010000000002',
            status='pending',
            pay_method='offline',
            receiver_name='测试用户',
            receiver_phone='13800138000',
            receiver_address='幸福社区 8 栋',
            items_amount=20,
            delivery_fee=3,
            total_amount=23,
            items_snapshot=[]
        )

        response = self.client.patch(
            f'/api/v1/orders/{order.id}/status',
            {'status': 'confirmed'},
            format='json',
            HTTP_AUTHORIZATION=f'Bearer django-token-{self.buyer.id}'
        )
        self.assertEqual(response.status_code, 403)


class ConcurrentOrderTests(TransactionTestCase):
    def setUp(self):
        self.merchant = Merchant.objects.create(
            name='并发测试超市',
            phone='020-99990001',
            address='并发路 1 号',
            delivery_note='测试配送',
            min_order_amount=1,
            delivery_fee=0,
            is_open=True
        )
        self.buyer_a = StoreUser.objects.create(
            username='buyer_a',
            password='pass1234',
            role='buyer',
            nickname='买家A',
            phone='13800001111'
        )
        self.buyer_b = StoreUser.objects.create(
            username='buyer_b',
            password='pass1234',
            role='buyer',
            nickname='买家B',
            phone='13800002222'
        )
        self.product = Product.objects.create(
            merchant=self.merchant,
            name='限量商品',
            price=10,
            unit='个',
            stock=1,
            is_active=True,
            image_url='',
            description='并发测试商品'
        )

    def _build_order_payload(self, buyer_id):
        return {
            'buyer_id': buyer_id,
            'merchant_id': self.merchant.id,
            'receiver_name': '测试',
            'receiver_phone': '13800001111',
            'receiver_address': '测试地址',
            'cart_items': [
                {'product_id': self.product.id, 'quantity': 1}
            ]
        }

    @skipIf(
        connection.vendor == 'sqlite',
        'SQLite 不支持 select_for_update 行级锁，无法真实模拟并发竞态'
    )
    def test_concurrent_order_only_one_succeeds(self):
        results = {}
        barrier = threading.Barrier(2, timeout=10)

        def place_order(buyer_id, key):
            barrier.wait()
            client = APIClient()
            try:
                response = client.post(
                    '/api/v1/orders',
                    self._build_order_payload(buyer_id),
                    format='json'
                )
                results[key] = response.status_code
            except Exception as exc:
                results[key] = str(exc)
            finally:
                connection.close()

        t1 = threading.Thread(target=place_order, args=(self.buyer_a.id, 'a'))
        t2 = threading.Thread(target=place_order, args=(self.buyer_b.id, 'b'))
        t1.start()
        t2.start()
        t1.join(timeout=15)
        t2.join(timeout=15)

        status_codes = list(results.values())
        self.assertEqual(status_codes.count(201), 1, f'恰好一笔下单应成功，实际状态码: {results}')
        self.assertEqual(status_codes.count(400), 1, f'另一笔应返回 400，实际状态码: {results}')

        self.product.refresh_from_db()
        self.assertGreaterEqual(self.product.stock, 0, f'库存不得为负，实际: {self.product.stock}')
        self.assertEqual(self.product.stock, 0)
        self.assertEqual(Order.objects.count(), 1)

    def test_sequential_stock_exhaustion(self):
        client = APIClient()

        resp1 = client.post(
            '/api/v1/orders',
            self._build_order_payload(self.buyer_a.id),
            format='json'
        )
        self.assertEqual(resp1.status_code, 201)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 0)

        resp2 = client.post(
            '/api/v1/orders',
            self._build_order_payload(self.buyer_b.id),
            format='json'
        )
        self.assertEqual(resp2.status_code, 400)

        self.product.refresh_from_db()
        self.assertGreaterEqual(self.product.stock, 0, f'库存不得为负，实际: {self.product.stock}')
        self.assertEqual(Order.objects.count(), 1)

    def test_zero_stock_rejects_order(self):
        self.product.stock = 0
        self.product.save(update_fields=['stock'])

        client = APIClient()
        resp = client.post(
            '/api/v1/orders',
            self._build_order_payload(self.buyer_a.id),
            format='json'
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Order.objects.count(), 0)

    def test_unlimited_stock_allows_order(self):
        self.product.stock = -1
        self.product.save(update_fields=['stock'])

        client = APIClient()
        resp = client.post(
            '/api/v1/orders',
            self._build_order_payload(self.buyer_a.id),
            format='json'
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(Order.objects.count(), 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, -1)
