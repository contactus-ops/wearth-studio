import os, requests as _r
from flask import request, jsonify

def product_colors():
    product = request.args.get('product', '').strip()
    exclude = request.args.get('exclude', '').strip().lower()
    store = os.environ.get('SHOPIFY_STORE', '')
    token = os.environ.get('SHOPIFY_TOKEN', '')
    if not product or not store or not token:
        return jsonify({'colors': []})
    try:
        resp = _r.get(
            'https://' + store + '/admin/api/2024-01/products.json',
            params={'title': product, 'fields': 'id,handle,variants', 'limit': 1},
            headers={'X-Shopify-Access-Token': token}, timeout=8)
        if resp.status_code != 200: return jsonify({'colors': []})
        products = resp.json().get('products', [])
        if not products: return jsonify({'colors': []})
        p = products[0]
        seen, out = set(), []
        for v in p.get('variants', []):
            color = v.get('title', '').split(' / ')[0].strip()
            if not color or color.lower() == exclude or color in seen: continue
            if v.get('inventory_quantity', 0) <= 0: continue
            seen.add(color)
            url = 'https://wearthactive.com/products/' + p.get('handle', '') + '?variant=' + str(v['id'])
            out.append({'color': color, 'url': url})
        return jsonify({'colors': out})
    except Exception as e:
        return jsonify({'colors': [], 'error': str(e)})