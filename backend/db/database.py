from sqlmodel import SQLModel, create_engine, Session
from core.config import settings

# 1. Initialize the MySQL Engine Connection Pool
# We append +pymysql to specify our connection driver interface explicitly
engine = create_engine(
    settings.DATABASE_PUBLIC_URL,
    echo=False,
    pool_recycle=3600,  # Closes inactive connections before MySQL kills them automatically
    pool_pre_ping=True   # Validates that connection sockets are alive before executing a query
)

# 2. Database Dependency Injection Handler
def get_session():
    """
    FastAPI Dependency yielding a clean transactional database session.
    """
    with Session(engine) as session:
        yield session

# 3. Tables Initializer Script
def init_db():
    """
    Reads active global meta tables and automatically creates physical 
    MySQL database schemas if they are missing.
    """
    from models.case import Case, ValidationError
    SQLModel.metadata.create_all(engine)