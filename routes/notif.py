from fastapi import APIRouter, Request
import httpx
from config import BOT_TOKEN

router = APIRouter()

@router.post("/notif")
async def notif(request: Request):
    data = await request.json()
    user_id = data.get("user_id")
    message = data.get("message")

    async with httpx.AsyncClient() as client:
        await client.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": user_id, "text": message}
        )
    return {"status": "ok"}
