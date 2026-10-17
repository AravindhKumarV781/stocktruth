# Fabric notebook (PySpark). Create a notebook in your workspace, attach the Lakehouse, paste each
# "# %%" block into its own cell, and run top to bottom.
# Purpose: turn the uploaded CSVs into Delta tables so Power BI and the SQL endpoint can use them.

# %% Cell 1: load source tables
tables = ["products", "suppliers", "locations", "pos_sales", "grn", "returns",
          "wms_moves", "adjustments", "pick_exceptions", "stock_counts", "golden_cases"]
for t in tables:
    df = (spark.read.option("header", True).option("inferSchema", True)
          .csv(f"Files/stocktruth/data/{t}.csv"))
    df.write.mode("overwrite").format("delta").saveAsTable(t)
    print(t, df.count())

# %% Cell 2: the Variance Detector as SQL (same logic as the Python detector) -> table `variance_cases`
spark.sql("""
CREATE OR REPLACE TABLE variance_cases AS
SELECT c.location, c.sku, p.name AS product, p.category, p.supplier_id,
       SUM(c.system_qty - c.counted_qty)                            AS net_variance,
       MAX(ABS(c.system_qty - c.counted_qty))                       AS max_bin_variance,
       GREATEST(ABS(SUM(c.system_qty - c.counted_qty)),
                SUM(ABS(c.system_qty - c.counted_qty)) DIV 2) * p.unit_cost AS value_at_risk_inr
FROM stock_counts c JOIN products p ON p.sku = c.sku
WHERE c.count_date = (SELECT MAX(count_date) FROM stock_counts)
GROUP BY c.location, c.sku, p.name, p.category, p.supplier_id, p.unit_cost
HAVING SUM(c.system_qty - c.counted_qty) <> 0 OR MAX(ABS(c.system_qty - c.counted_qty)) <> 0
""")
display(spark.sql("SELECT * FROM variance_cases ORDER BY value_at_risk_inr DESC"))

# %% Cell 3: after running the pipeline and `01_upload_to_onelake.py --results`, load results for Power BI
res = (spark.read.option("header", True).option("inferSchema", True)
       .csv("Files/stocktruth/results/case_results.csv"))
res.write.mode("overwrite").format("delta").saveAsTable("case_results")
display(res)
