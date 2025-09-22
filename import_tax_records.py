from pymongo import MongoClient
import pandas as pd
import os
from dotenv import load_dotenv

def main():
    # 1) Load CSV
    df = pd.read_csv("tax_records.csv")

    # 2) Connect to Atlas
    load_dotenv()
    mongo_uri  = os.environ["MONGO_URI"]
    db_name    = os.environ["MONGO_DB"]
    coll_name  = os.environ["MONGO_COLL"]

    client = MongoClient(mongo_uri)
    db = client[db_name]
    coll = db[coll_name]

    # 3) Wipe existing documents (optional)
    coll.delete_many({})

    # 4) Insert all rows
    records = df.to_dict("records")
    result = coll.insert_many(records)

    print(f"Imported {len(result.inserted_ids)} documents into {db_name}.{coll_name}")

if __name__ == "__main__":
    main()
