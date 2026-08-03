import sys

sys.path.insert(0, ".")

from Core.Database.DatabaseService import DatabaseService


# directive: ingest-pipeline-kiss
def Main():
    Db = DatabaseService()
    Db.ExecuteNonQuery("DROP TABLE IF EXISTS OnDemandProbeRequests CASCADE")
    Db.ExecuteNonQuery("DROP TABLE IF EXISTS OnDemandScanRequests CASCADE")
    print("Dropped OnDemandProbeRequests + OnDemandScanRequests.")
    return 0


if __name__ == "__main__":
    sys.exit(Main())
