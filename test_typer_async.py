# test_typer_async.py (Modified for direct asyncio test)
import asyncio

async def hello_direct(name: str): # Just a regular async function now
    """Says hello."""
    await asyncio.sleep(0.1) 
    print(f"Hello {name} from direct asyncio test!")

if __name__ == "__main__":
    # Get command line argument manually for this test
    import sys
    if len(sys.argv) > 1:
        name_arg = sys.argv[1]
        asyncio.run(hello_direct(name_arg))
    else:
        print("Please provide a name as an argument.")