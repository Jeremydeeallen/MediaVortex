import sys, os
sys.path.insert(0, '.')
from Core.Database.DatabaseService import DatabaseService
from Core.PathStorage import LoadStorageRoots, Parse, Resolve
DB = DatabaseService()
SR = LoadStorageRoots(DB)
P = r'T:\Suits\Season 7\Suits - S07E16 - Good-Bye WEBDL-480p.mkv'
SrId, Rel = Parse(P, SR)
Local = Resolve(SrId, Rel, 'larry-worker-1', DB)
print(f'Local={Local}')
print(f'Exists={os.path.exists(Local)}')
