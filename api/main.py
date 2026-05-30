from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
import logging
from models import EventIngestRequest, EventIngestResponse

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Store Intelligence API",
    description="Real-time retail analytics backend",
    version="1.0.0"
)

@app.get("/health", tags=["System"])
async def health_check():
    """Endpoint for Docker to verify the API is ready to accept traffic."""
    return {"status": "healthy"}

@app.post(
    "/events/ingest", 
    response_model=EventIngestResponse, 
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Ingestion"]
)
async def ingest_events(payload: EventIngestRequest):
    """
    Accepts a batch of events from the computer vision pipeline.
    FastAPI and Pydantic automatically validate the schema before this code runs.
    """
    try:
        # TODO: Add SQLAlchemy Database Insertion Logic Here
        # For now, we just acknowledge receipt to prove the API works.
        
        event_count = len(payload.events)
        logger.info(f"Received batch of {event_count} events.")
        
        # Example of how to iterate through validated events:
        # for event in payload.events:
        #     logger.debug(f"Processing event {event.event_id} for visitor {event.visitor_id}")

        return EventIngestResponse(
            status="success",
            processed_count=event_count
        )

    except Exception as e:
        logger.error(f"Failed to process event batch: {str(e)}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"status": "error", "message": "Internal server error during ingestion"}
        )