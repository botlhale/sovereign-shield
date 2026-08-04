import os
from pyspark.sql import SparkSession

def apply_security_layer():
    spark = SparkSession.builder.getOrCreate()
    
    # In Databricks interactive environments, __file__ is not defined.
    # We use os.getcwd() which points to the root of the bundle files.
    cwd = os.getcwd()
    sql_path = os.path.join(cwd, "src", "unity_catalog_triple_lock.sql")
    
    # Fallback just in case the working directory resolves directly to the src folder
    if not os.path.exists(sql_path):
        sql_path = os.path.join(cwd, "unity_catalog_triple_lock.sql")
        
    print(f"Reading SQL architecture from: {sql_path}")
    
    with open(sql_path, "r") as file:
        sql_content = file.read()
        
    # Split the file by semicolons to execute each statement individually
    statements = [stmt.strip() for stmt in sql_content.split(';') if stmt.strip()]
    
    for statement in statements:
        print(f"Executing: {statement[:60]}...")
        spark.sql(statement)
        
    print("Zero-Trust Security Layer established successfully!")

if __name__ == "__main__":
    apply_security_layer()