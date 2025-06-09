import asyncio
from multiprocessing import cpu_count


def create_delayed(callback, concurrency=cpu_count() + 1):
    sem = asyncio.Semaphore(concurrency)

    async def callback_with_semaphore(*args, **kwargs):
        async with sem:
            return await callback(*args, **kwargs)

    return callback_with_semaphore
