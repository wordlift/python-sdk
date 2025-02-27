import asyncio
from os import cpu_count


def delayed(callback, concurrency=cpu_count() + 1):
    sem = asyncio.Semaphore(concurrency)

    async def callback_with_semaphore(row):
        async with sem:
            return await callback(row)

    return callback_with_semaphore
