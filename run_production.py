import subprocess
import sys
import time
import os

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PYTHON_EXE = sys.executable
SCRIPT_PATH = os.path.join(os.path.dirname(__file__), 'bot.py')

def run_supervisor():
    print('=' * 60)
    print('Abyssinia Market Bot - Production Supervisor Started')
    print('Target:', SCRIPT_PATH)
    print('Python:', PYTHON_EXE)
    print('=' * 60)
    restart_count = 0
    while True:
        proc = None
        try:
            now_str = time.strftime('%Y-%m-%d %H:%M:%S')
            print(f'[{now_str}] Starting bot.py (Run #{restart_count + 1})...')
            proc = subprocess.Popen([PYTHON_EXE, SCRIPT_PATH])
            proc.wait()
            return_code = proc.returncode
            print(f'[{now_str}] bot.py exited with code {return_code}.')
        except KeyboardInterrupt:
            print('\nSupervisor received KeyboardInterrupt. Stopping bot...')
            if proc and proc.poll() is None:
                proc.terminate()
                proc.wait()
            break
        except Exception as ex:
            print(f'Supervisor error: {ex}')
        restart_count += 1
        print(f'Restarting bot in 5 seconds (Restart #{restart_count})...')
        time.sleep(5)

if __name__ == '__main__':
    run_supervisor()
