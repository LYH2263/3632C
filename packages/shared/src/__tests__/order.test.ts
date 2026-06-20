import { describe, expect, it } from 'vitest';
import type { Merchant, Product } from '../types';
import {
  canTransitionStatus,
  createOrderFromCart,
  emptyCart,
  seedMerchants,
  seedProducts,
  validateCartForCheckout
} from '../index';

describe('订单状态机', () => {
  it('支持 pending -> confirmed，不支持 completed -> pending', () => {
    expect(canTransitionStatus('pending', 'confirmed')).toBe(true);
    expect(canTransitionStatus('completed', 'pending')).toBe(false);
  });
});

describe('购物车校验', () => {
  it('库存不足时阻止提交', () => {
    const merchant = seedMerchants[0];
    const cart = {
      merchant_id: merchant.id,
      updated_at: new Date().toISOString(),
      items: [{ product_id: 1001, quantity: 999 }]
    };

    const validation = validateCartForCheckout(
      cart,
      merchant,
      seedProducts.filter((item) => item.merchant_id === merchant.id)
    );
    expect(validation.valid).toBe(false);
    expect(validation.errors.join('')).toContain('超过库存限制');
  });

  it('空购物车应返回错误', () => {
    const merchant = seedMerchants[0];
    const cart = {
      ...emptyCart,
      merchant_id: merchant.id
    };
    const validation = validateCartForCheckout(
      cart,
      merchant,
      seedProducts.filter((item) => item.merchant_id === merchant.id)
    );
    expect(validation.valid).toBe(false);
    expect(validation.errors).toContain('购物车为空');
  });
});

describe('下单创建', () => {
  it('起送价满足后可创建 pending 订单且支付方式为 offline', () => {
    const merchant = seedMerchants[1];
    const cart = {
      merchant_id: merchant.id,
      updated_at: new Date().toISOString(),
      items: [
        { product_id: 2001, quantity: 2 },
        { product_id: 2002, quantity: 1 }
      ]
    };

    const order = createOrderFromCart({
      orderId: 1,
      buyerId: 1,
      payload: {
        buyer_id: 1,
        merchant_id: merchant.id,
        receiver_name: '测试用户',
        receiver_phone: '13800138000',
        receiver_address: '幸福社区 8 栋',
        remark: '请尽快配送'
      },
      merchant,
      cart,
      products: seedProducts.filter((item) => item.merchant_id === merchant.id)
    });

    expect(order.status).toBe('pending');
    expect(order.pay_method).toBe('offline');
    expect(order.items_snapshot.length).toBe(2);
    expect(order.total_amount).toBeGreaterThan(order.items_amount);
  });
});

describe('库存边界校验', () => {
  const baseMerchant: Merchant = {
    id: 9001,
    name: '边界测试商家',
    phone: '020-00000001',
    address: '测试地址',
    delivery_note: '',
    min_order_amount: 1,
    delivery_fee: 0,
    is_open: true
  };

  function makeProduct(overrides: Partial<Product> = {}): Product {
    return {
      id: 8001,
      merchant_id: baseMerchant.id,
      name: '边界商品',
      price: 10,
      unit: '个',
      stock: 5,
      is_active: true,
      image_url: '',
      description: '',
      ...overrides
    };
  }

  function makeCart(productId: number, quantity: number) {
    return {
      merchant_id: baseMerchant.id,
      updated_at: new Date().toISOString(),
      items: [{ product_id: productId, quantity }]
    };
  }

  it('stock=-1 表示不限库存，任意数量均可通过', () => {
    const product = makeProduct({ stock: -1 });
    const cart = makeCart(product.id, 9999);
    const result = validateCartForCheckout(cart, baseMerchant, [product]);
    expect(result.valid).toBe(true);
    expect(result.errors).toHaveLength(0);
  });

  it('stock=0 库存为零时应拒绝下单', () => {
    const product = makeProduct({ stock: 0 });
    const cart = makeCart(product.id, 1);
    const result = validateCartForCheckout(cart, baseMerchant, [product]);
    expect(result.valid).toBe(false);
    expect(result.errors.join('')).toContain('超过库存限制');
  });

  it('stock=1 且购买数量=1 时应通过', () => {
    const product = makeProduct({ stock: 1 });
    const cart = makeCart(product.id, 1);
    const result = validateCartForCheckout(cart, baseMerchant, [product]);
    expect(result.valid).toBe(true);
  });

  it('stock=1 且购买数量=2 时应拒绝', () => {
    const product = makeProduct({ stock: 1 });
    const cart = makeCart(product.id, 2);
    const result = validateCartForCheckout(cart, baseMerchant, [product]);
    expect(result.valid).toBe(false);
    expect(result.errors.join('')).toContain('超过库存限制');
  });
});
