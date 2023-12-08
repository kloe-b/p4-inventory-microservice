from flask import Flask, jsonify, request
import os
from flask_cors import CORS
from database import db, Item,bcrypt
from redis import Redis
import requests
import json
import threading
import logging
from opentelemetry import trace
from prometheus_client import Counter, generate_latest
from flask import Response
from flask import Response
from opentelemetry import trace
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv.resource import ResourceAttributes


service_name = "my-inventory-service" 
resource = Resource(attributes={
    ResourceAttributes.SERVICE_NAME: service_name
})
app = Flask(__name__)

trace.set_tracer_provider(TracerProvider(resource=resource))

otlp_exporter = OTLPSpanExporter(
    endpoint="http://localhost:4317",  
    insecure=True
)

trace.get_tracer_provider().add_span_processor(BatchSpanProcessor(otlp_exporter))

FlaskInstrumentor().instrument_app(app)

tracer = trace.get_tracer(__name__)

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s:%(name)s: %(message)s')
logger = logging.getLogger(__name__) 

basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] =\
        'sqlite:///' + os.path.join(basedir, 'database.db')
  
db.init_app(app)
bcrypt.init_app(app)

REDIS_HOST = os.environ.get('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.environ.get('REDIS_PORT', 6379))
r = Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

inventory_failure_counter = Counter('inventory_failure_total', 'Total number of failed inventory changes')

@app.route('/metrics')
def serve_metrics():
    return Response(generate_latest(), mimetype="text/plain")

@app.route('/inventory/<int:product_id>', methods=['GET', 'PUT'])
def manage_inventory(product_id):
    with tracer.start_as_current_span("manage_inventory") as span:
        span.set_attribute("product_id", product_id)
        logger.info(f"Received request to manage inventory for product_id: {product_id}")
        if request.method == 'GET':
            item = Item.query.filter_by(id=product_id).first()
            if item:
                return jsonify(item.to_dict())
            return jsonify({'error': 'Item not found'}), 404

        if request.method == 'PUT':
            data = request.json
            logger.info(f"Updating inventory for product_id {product_id} with data: {data}")
            item = Item.query.filter_by(id=product_id).first()
            if item:
                item.quantity += data.get('quantity_change', 0)
                db.session.commit()
                return jsonify(item.to_dict())
            return jsonify({'error': 'Item not found'}), 404

def handle_payment_event(message):
    with tracer.start_as_current_span("handle_payment_event"):
            logger.info("Starting payment status listener")
            data = json.loads(message['data'])
            logger.info(f"Received data: {data}")

            order_id = data['order_id']
            status = data['status']
            product_id = data['product_id']  
            quantity = data['amount']

            if status == 'SUCCESS':
                confirm_inventory_reservation(order_id,product_id, quantity)
            else:
                release_inventory_reservation(product_id, quantity)

def confirm_inventory_reservation(order_id,product_id, quantity):
    with app.app_context():
        with tracer.start_as_current_span("confirm_inventory_reservation") as span:
            logger.info(f"Confirming inventory reservation for order_id {order_id}, product_id {product_id}")
            item = Item.get_or_create(product_id)
            if item:
                if item.quantity<quantity:
                    print(f"no stock left: ")
                    inventory_failure_counter.inc()
                    r.publish('inventory_failure', json.dumps({'order_id':order_id , 'status': 'ofs', 'product_id': product_id}))
                else:   
                    item.quantity -= quantity  
                    db.session.commit()
                    r.publish('inventory_update', json.dumps({'order_id':order_id , 'status': 'reserved', 'product_id': product_id,'quantity':quantity}))

def release_inventory_reservation(product_id, quantity):
    logger.info(f"Releasing inventory reservation for product_id {product_id}")
    item = Item.query.filter_by(id=product_id).first()
    if item:
        item.quantity += quantity
        db.session.commit()
        r.publish('inventory_update', json.dumps({'order_id':order_id , 'status': 'open', 'product_id': product_id}))
           

def handle_delivery_event(message):
    with tracer.start_as_current_span("handle_delivery_event"):
        logger.info("Starting delivery status listener")
        data = json.loads(message['data'])
        order_id = data['order_id']
        product_id = data['product_id']
        quantity = data['quantity']
        status = data['status']

        if status == 'FAILED':
            handle_delivery_failure(product_id,quantity)


def handle_delivery_failure(product_id):
    with app.app_context():
        item = Item.query.filter_by(id=product_id).first()
        if item:
            item.quantity += quantity  
            db.session.commit()
            r.publish('inventory_failure', json.dumps({'order_id':order_id , 'status': 'delivery', 'product_id': product_id}))
            print(f"Delivery failure for product {product_id}, inventory adjusted.")

def start_listeners():
    with tracer.start_as_current_span("start_listeners"):
        pubsub = r.pubsub()
        pubsub.subscribe(**{
            'payment_status': handle_payment_event,
            'delivery_status': handle_delivery_event  
        })
        logger.info("Starting listeners")
        for message in pubsub.listen():
            if message['type'] == 'message':
                if message['channel'] == 'payment_status':
                    handle_payment_event(message)
                elif message['channel'] == 'delivery_status':
                    handle_delivery_event(message)


if __name__ == '__main__':
    logger.info("Starting Flask application and initializing database")
    with app.app_context():
        db.create_all()
    logger.info("Database initialized")
    thread = threading.Thread(target=start_listeners)
    thread.start()
    logger.info("Background thread for payment status listener started")

    app.run(debug=True, port=5002)

