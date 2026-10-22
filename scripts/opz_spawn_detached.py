"""Start a Windows server without leaking the launcher's pipeline handles."""
import json
import os
import subprocess
import sys


def main() -> None:
    if os.name != 'nt':
        raise SystemExit('Windows launcher only')
    with open(sys.argv[1], encoding='utf-8-sig') as source:
        request = json.load(source)
    command = subprocess.list2cmdline([request['executable']]) + ' ' + request['arguments']
    with open(request['stdout'], 'wb') as stdout, open(request['stderr'], 'wb') as stderr:
        child = subprocess.Popen(command, executable=request['executable'], cwd=request['cwd'],
            stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr, close_fds=True,
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
    print(child.pid)


if __name__ == '__main__':
    main()
