# typer_minimal_async_test.py
import typer
import asyncio # Keep asyncio import for the await asyncio.sleep

app = typer.Typer()

@app.command()
async def minimal_hello(name: str):
    """A minimal async Typer command."""
    await asyncio.sleep(0.01) # A very short await
    print(f"Minimal hello to {name} (Typer async)")

if __name__ == "__main__":
    app()