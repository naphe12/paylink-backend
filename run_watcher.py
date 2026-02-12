import asyncio
from app.watchers.polygon_polling_watcher import PolygonPollingWatcher

async def main():
    watcher = PolygonPollingWatcher()
    await watcher.run()

if __name__ == "__main__":
    asyncio.run(main())
