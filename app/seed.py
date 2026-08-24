from app.db import Base, SessionLocal, engine
from app.main import seed_plans

Base.metadata.create_all(bind=engine)
db = SessionLocal()
try:
    seed_plans(db)
finally:
    db.close()
print("database ready")
