import pandas as pd
for f in ["customers", "customer_segments", "orders"]:
    d = pd.read_csv(f"data/raw/{f}.csv")
    print(f, d.shape)
    print(d.head(3))
    print(d.isna().sum().to_dict())
    print(d.nunique().to_dict())
