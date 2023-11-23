from flask import Flask, request, jsonify, Blueprint
from database import Item, db
from redis import Redis
import requests
import json
import os
import logging
from opentelemetry import trace
from opentelemetry import metrics

inventory_service = Blueprint("inventory_service", __name__)

SECRET_KEY = 'your_secret_key'
REDIS_HOST = os.environ.get('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.environ.get('REDIS_PORT', 6379))
ORDER_SERVICE_URL = "http://127.0.0.1:8080" 
PAYMENT_SERVICE_URL = "http://127.0.0.1:8081" 

r = Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
pubsub = r.pubsub()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

tracer = trace.get_tracer("...tracer")
meter = metrics.get_meter("...meter")

@inventory_service.route('/inventory/<int:item_id>', methods=['GET'])
def check_inventory(item_id):
    order_response = requests.get(f"{ORDER_SERVICE_URL}/orders/{item_id}")
    order_details = order_response.json()
    user_id = order_details['customer_id']
    item = Item.query.get(user_id)
    if item:
        return jsonify(item.to_dict())
    else:
        item = Item(id=user_id,quantity=10, name="Item Name")  # Set initial_credits as per your business logic
        db.session.add(item)
        db.session.commit()
        return jsonify(item.to_dict), 201

@inventory_service.route('/inventory/update', methods=['POST'])
def update_inventory():
    update_data = request.json
    item_id = update_data['item_id']
    quantity_change = update_data['quantity_change']

    item = Item.query.get(item_id)
    if not item:
        notify_payment_service(item_id, success=False)
        return jsonify({'error': 'Item not found'}), 404

    try:
        item.quantity += quantity_change
        if item.quantity < 0:
            raise Exception('Insufficient stock')

        db.session.commit()
        notify_payment_service(item_id, success=True)
        return jsonify({'message': 'Inventory updated successfully'})
    except Exception as e:
        db.session.rollback()
        notify_payment_service(item_id, success=False)
        return jsonify({'error': 'Inventory update failed', 'message': str(e)}), 500

def notify_payment_service(item_id, success):
    message = json.dumps({'item_id': item_id, 'success': success})
    r.publish('inventory_update', message)

