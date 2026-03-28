import httpx
import asyncio

async def main():
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post("http://localhost:8081/api/v1/chaos", json={"type": "cpu_stress"}, timeout=5.0)
            print(resp.status_code)
            print(resp.text)
    except Exception as e:
        print(e)

if __name__ == "__main__":
    asyncio.run(main())
