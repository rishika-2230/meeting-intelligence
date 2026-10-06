from fastapi import FastAPI, Request
from datetime import datetime

app = FastAPI(
    title="Meeting Intelligence Fireflies Webhook"
)


@app.get("/")
def health_check():
    return {
        "status": "online",
        "service": "Meeting Intelligence Fireflies Webhook"
    }


@app.post("/webhook/fireflies")
async def fireflies_webhook(request: Request):

    payload = await request.json()

    print("\n" + "=" * 60)
    print("FIREFLIES WEBHOOK RECEIVED")
    print("Time:", datetime.now())
    print("Payload:", payload)
    print("=" * 60)

    return {
        "status": "received"
    }