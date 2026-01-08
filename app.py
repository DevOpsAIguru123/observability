import logging
import time
import random
import random
# import threading (removed)
# import requests (removed)
import uvicorn
import uvicorn
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Boolean
from sqlalchemy.orm import sessionmaker, declarative_base, Session

# OpenTelemetry Imports
from opentelemetry import trace, metrics
from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv.resource import ResourceAttributes
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter

# Instrumentation Imports
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

# --- 1. CONFIGURATION ---
SERVICE_NAME = "todo_service"
OTEL_COLLECTOR_HTTP = "http://otel-collector:4318"
DATABASE_URL = "postgresql://user:password@postgres:5432/todo_db"

resource = Resource(attributes={
    ResourceAttributes.SERVICE_NAME: SERVICE_NAME
})

# --- 2. OBSERVABILITY SETUP ---

# Traces
trace_provider = TracerProvider(resource=resource)
span_exporter = OTLPSpanExporter(endpoint=f"{OTEL_COLLECTOR_HTTP}/v1/traces")
trace_provider.add_span_processor(BatchSpanProcessor(span_exporter))
trace.set_tracer_provider(trace_provider)
tracer = trace.get_tracer(__name__)

# Metrics
metric_reader = PeriodicExportingMetricReader(
    OTLPMetricExporter(endpoint=f"{OTEL_COLLECTOR_HTTP}/v1/metrics"),
    export_interval_millis=5000
)
meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
metrics.set_meter_provider(meter_provider)

# Logs
logger_provider = LoggerProvider(resource=resource)
log_exporter = OTLPLogExporter(endpoint=f"{OTEL_COLLECTOR_HTTP}/v1/logs")
logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))
handler = LoggingHandler(logger_provider=logger_provider, level=logging.NOTSET)
logging.basicConfig(level=logging.INFO, handlers=[handler, logging.StreamHandler()])
logger = logging.getLogger("todo_app")

# --- 3. DATABASE SETUP ---
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class TodoItem(Base):
    __tablename__ = "todos"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    done = Column(Boolean, default=False)

# Create tables
def init_db():
    # Wait for DB to be ready
    for i in range(10):
        try:
            Base.metadata.create_all(bind=engine)
            logger.info("Database initialized successfully.")
            return
        except Exception as e:
            logger.warning(f"Database not ready yet, retrying... ({e})")
            time.sleep(2)
    logger.error("Could not connect to database.")

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- 4. FASTAPI APP ---
app = FastAPI(title="Observability ToDo App")

# Serve Backend API
# Instrument FastAPI
FastAPIInstrumentor.instrument_app(app)
# Instrument SQLAlchemy
SQLAlchemyInstrumentor().instrument(engine=engine)

# Serve Frontend
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def read_root():
    return FileResponse('static/index.html')

class TodoCreate(BaseModel):
    title: str

class TodoResponse(BaseModel):
    id: int
    title: str
    done: bool
    class Config:
        orm_mode = True

@app.get("/todos", response_model=List[TodoResponse])
def read_todos(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    logger.info("Fetching todos list")
    todos = db.query(TodoItem).offset(skip).limit(limit).all()
    # Manual span to show extra detail
    with tracer.start_as_current_span("calculate_stats"):
        done_count = sum(1 for t in todos if t.done)
        logger.info(f"Found {len(todos)} todos, {done_count} completed.")
    return todos

@app.post("/todos", response_model=TodoResponse)
def create_todo(todo: TodoCreate, db: Session = Depends(get_db)):
    logger.info(f"Creating todo: {todo.title}")
    
    # Simulate occasional random error (REMOVED)
    # if random.random() < 0.1:
    #     logger.error("Database connection flake simulated!")
    #     raise HTTPException(status_code=500, detail="Internal Server Flake")

    db_todo = TodoItem(title=todo.title)
    db.add(db_todo)
    db.commit()
    db.refresh(db_todo)
    return db_todo

@app.put("/todos/{todo_id}/done", response_model=TodoResponse)
def mark_done(todo_id: int, db: Session = Depends(get_db)):
    logger.info(f"Marking todo {todo_id} as done")
    todo = db.query(TodoItem).filter(TodoItem.id == todo_id).first()
    if not todo:
        logger.warning(f"Todo {todo_id} not found")
        raise HTTPException(status_code=404, detail="Todo not found")
    todo.done = True
    db.commit()
    db.refresh(todo)
    return todo

@app.delete("/todos/{todo_id}")
def delete_todo(todo_id: int, db: Session = Depends(get_db)):
    logger.info(f"Deleting todo {todo_id}")
    todo = db.query(TodoItem).filter(TodoItem.id == todo_id).first()
    if not todo:
        logger.warning(f"Todo {todo_id} not found")
        raise HTTPException(status_code=404, detail="Todo not found")
    db.delete(todo)
    db.commit()
    return {"ok": True}

# --- 5. TRAFFIC SIMULATOR ---
def traffic_simulator():
    """Background thread to generate traffic so user sees traces immediately."""
    logger.info("Starting traffic simulator...")
    time.sleep(5) # Wait for app to start
    base_url = "http://localhost:8000"
    
    actions = ["create", "list", "done", "error_trigger"]
    
    while True:
        try:
            action = random.choice(actions)
            
            if action == "create":
                title = f"Task-{random.randint(1000, 9999)}"
                requests.post(f"{base_url}/todos", json={"title": title})
                
            elif action == "list":
                requests.get(f"{base_url}/todos")
                
            elif action == "done":
                # Try to mark a random ID done
                todo_id = random.randint(1, 20) 
                requests.put(f"{base_url}/todos/{todo_id}/done")
                
            elif action == "error_trigger":
                # Create a task that might trigger the 10% flake
                title = "Flaky Task"
                requests.post(f"{base_url}/todos", json={"title": title})
                
            time.sleep(random.uniform(0.5, 2.0))
            
        except Exception as e:
            logger.debug(f"Simulator error (expected during startup): {e}")
            time.sleep(5)

if __name__ == "__main__":
    # Start Traffic Simulator in background (REMOVED)
    # sim_thread = threading.Thread(target=traffic_simulator, daemon=True)
    # sim_thread.start()
    
    # Initialize DB (Simple Retry Logic inside)
    init_db()
    
    # Start App
    uvicorn.run(app, host="0.0.0.0", port=8000)
