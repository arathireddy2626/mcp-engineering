"""
Seed the database with initial data.
Run once before starting the server for the first time.
Usage: python scripts/seed.py
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from server.db import init_db, DB_PATH

async def main():
    print(f"Initializing database at: {DB_PATH}")
    await init_db()
    print("Done. Schema created and mock data seeded.")

if __name__ == "__main__":
    asyncio.run(main())
