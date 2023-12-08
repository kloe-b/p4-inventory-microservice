from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
import datetime

db = SQLAlchemy()
bcrypt = Bcrypt()

class Item(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)
    quantity = db.Column(db.Integer, nullable=False,default=100)

    def to_dict(self):
        return {
            'id': self.id,
            'name':self.name,
            'quantity': self.quantity
        }

    @staticmethod
    def get_or_create(item_id):
        item = Item.query.get(item_id)
        if not item:
            item = Item(id=item_id,name='token')
            db.session.add(item)
            db.session.commit()
        return item

