from flask import Flask, jsonify, request
import os
from flask_cors import CORS
from database import db, Item,bcrypt
from redis import Redis
import requests
import json
import threading
import logging

app = Flask(__name__)
    
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] =\
        'sqlite:///' + os.path.join(basedir, 'database.db')
  
db.init_app(app)
bcrypt.init_app(app)

REDIS_HOST = os.environ.get('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.environ.get('REDIS_PORT', 6379))
r = Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

@app.route('/inventory/<int:product_id>', methods=['GET', 'PUT'])
def manage_inventory(product_id):
    if request.method == 'GET':
        item = Item.query.filter_by(id=product_id).first()
        if item:
            return jsonify(item.to_dict())
        return jsonify({'error': 'Item not found'}), 404

    if request.method == 'PUT':
        data = request.json
        item = Item.query.filter_by(id=product_id).first()
        if item:
            item.quantity += data.get('quantity_change', 0)
            db.session.commit()
            return jsonify(item.to_dict())
        return jsonify({'error': 'Item not found'}), 404

def handle_payment_event(message):
    data = json.loads(message['data'])
    order_id = data['order_id']
    status = data['status']
    product_id = data['product_id']  # Assuming this is included in the event data
    quantity = data['amount']
    # product_id, quantity = extract_order_details(order_id)  

    if status == 'SUCCESS':
        confirm_inventory_reservation(product_id, quantity)
    else:
        release_inventory_reservation(product_id, quantity)

def confirm_inventory_reservation(product_id, quantity):
    with app.app_context():
        item = Item.get_or_create(product_id)
        # db.session.get(Item,product_id)
        if item:
            item.quantity -= quantity  
            db.session.commit()
            print(f"Payment sucess event received: ")

def release_inventory_reservation(product_id, quantity):
    item = Item.query.filter_by(id=product_id).first()
    if item:
        item.quantity += quantity
        db.session.commit()
        print(f"Payment not sucess event received: ")

def start_listeners():
    pubsub = r.pubsub()
    pubsub.subscribe(**{'payment_status': handle_payment_event})
    for message in pubsub.listen():
        if message['type'] == 'message':
            handle_payment_event(message)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()

    listener_thread = threading.Thread(target=start_listeners)
    listener_thread.start()

    app.run(debug=True, port=5002)

