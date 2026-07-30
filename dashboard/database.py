from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

# Database instance
db = SQLAlchemy()

# Migration manager
migrate = Migrate()