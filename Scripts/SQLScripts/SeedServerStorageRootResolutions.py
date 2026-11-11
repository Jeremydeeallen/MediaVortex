# directive: farm-server
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService
from Features.Workers.WorkersRepository import WorkersRepository


SERVER_INSTANCE_NAME = 'mediavortex-server'
SERVER_MOUNTS = {'T': '/mnt/media_tv/', 'M': '/mnt/movies/', 'X': '/mnt/xxx/'}


# directive: farm-server | # see startup.S6 -- the farm server's bind mounts mirror the larry workers (CT 218), so canonical paths resolve identically
def Run():
    if not WorkersRepository().RegisterStorageRootResolutions(SERVER_INSTANCE_NAME, 'linux', SERVER_MOUNTS):
        print(f"FAILED: RegisterStorageRootResolutions for {SERVER_INSTANCE_NAME}")
        return 1
    Rows = DatabaseService().ExecuteQuery(
        "SELECT sr.Name, r.AbsolutePath, r.IsActive FROM StorageRootResolutions r "
        "JOIN StorageRoots sr ON sr.Id = r.StorageRootId WHERE r.WorkerName = %s ORDER BY sr.Name",
        (SERVER_INSTANCE_NAME,),
    )
    for R in Rows:
        print(f"  {SERVER_INSTANCE_NAME} {R.get('Name')}: {R.get('AbsolutePath')} active={R.get('IsActive')}")
    if len(Rows) != len(SERVER_MOUNTS):
        print(f"FAILED: expected {len(SERVER_MOUNTS)} rows, found {len(Rows)}")
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(Run())
