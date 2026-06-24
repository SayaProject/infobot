import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.environ["BOT_TOKEN"]
API_ID: int = int(os.environ["API_ID"])
API_HASH: str = os.environ["API_HASH"]
OWNER_ID: int = int(os.environ.get("OWNER_ID", 0))
PORT: int = int(os.environ.get("PORT", 8080))
