from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
import datetime

db = SQLAlchemy()
bcrypt = Bcrypt()

class Item(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    quantity = db.Column(db.Integer, default=10,nullable=False)
    name = db.Column(db.String, nullable=False)  # 'nullable=False' makes this field mandatory
   
    def to_dict(self):
        return {
            'id': self.id,
            'quantity': self.quantity,
            'name' : self.name
        }