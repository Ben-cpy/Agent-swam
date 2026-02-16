"""
Quick test script to verify server startup
"""
import sys
import os

# Fix Windows console encoding
if sys.platform == 'win32':
    try:
        import codecs
        if hasattr(sys.stdout, 'buffer'):
            sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        if hasattr(sys.stderr, 'buffer'):
            sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
    except (AttributeError, TypeError):
        pass
    os.environ['PYTHONIOENCODING'] = 'utf-8'

# Get project root and add backend to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
backend_path = os.path.join(project_root, 'backend')
sys.path.insert(0, backend_path)

# Change to backend directory for database operations
os.chdir(backend_path)

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
    print(f'  ./scripts/start_server.sh')
    print()
    print(f'Server will be available at: http://{settings.api_host}:{settings.api_port}')
    return True


if __name__ == '__main__':
    result = asyncio.run(test_startup())
    sys.exit(0 if result else 1)
