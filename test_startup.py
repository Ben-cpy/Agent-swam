"""
Quick test script to verify server startup
"""
import sys
import os

# Fix Windows console encoding
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
    os.environ['PYTHONIOENCODING'] = 'utf-8'

# Move to backend directory
os.chdir(os.path.join(os.path.dirname(__file__), 'backend'))

# Add to path
sys.path.insert(0, os.getcwd())

from config import settings
from database import init_db, async_session_maker
from runner.agent import LocalRunnerAgent
import asyncio


async def test_startup():
    print('=' * 50)
    print('AI Task Manager - Startup Test')
    print('=' * 50)
    print()

    print('[1/3] Testing database initialization...')
    try:
        await init_db()
        print('  SUCCESS: Database initialized')
    except Exception as e:
        print(f'  ERROR: {e}')
        return False

    print()
    print('[2/3] Testing runner registration...')
    try:
        async with async_session_maker() as db:
            await LocalRunnerAgent.register_local_runner(db)
        print('  SUCCESS: Runner registered')
    except Exception as e:
        print(f'  ERROR: {e}')
        return False

    print()
    print('[3/3] Testing server imports...')
    try:
        from main import app
        print('  SUCCESS: FastAPI app created')
        print(f'  Title: {app.title}')
        print(f'  Version: {app.version}')
    except Exception as e:
        print(f'  ERROR: {e}')
        return False

    print()
    print('=' * 50)
    print('All checks passed!')
    print('=' * 50)
    print()
    print(f'To start the server, run:')
    print(f'  cd backend')
    print(f'  ..\\venv\\Scripts\\python.exe main.py')
    print()
    print(f'Server will be available at: http://{settings.api_host}:{settings.api_port}')
    return True


if __name__ == '__main__':
    result = asyncio.run(test_startup())
    sys.exit(0 if result else 1)
