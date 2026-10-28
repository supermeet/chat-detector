"""Print the structure of a provided dataset so it can be mapped onto the pipeline schema."""
import sys

import pandas as pd

path = sys.argv[1] if len(sys.argv) > 1 else "data/provided/synthetic/train.parquet"
df = pd.read_parquet(path)
print(path, df.shape)
print(df.dtypes.to_string())
for c in ["msg_label", "reply_label", "person_label", "scenario", "template_split", "relationship", "app",
          "minor_involved", "source", "is_user"]:
    if c in df:
        print(f"\n--- {c} ---\n{df[c].value_counts(dropna=False).head(25).to_string()}")
print("\ntext missing share:", round(df["text"].isna().mean(), 3))
conv = df.groupby("conversation_id")
print("msgs/conv:", conv.size().describe().round(1).to_dict())
print("accounts/person:", df[~df.is_user].groupby("person_id").account_id.nunique().value_counts().head(8).to_dict())
print("persons/conv:", conv.person_id.nunique().value_counts().to_dict())
print("\nscenario x person_label:\n", pd.crosstab(df.drop_duplicates("conversation_id").scenario,
                                                  df.drop_duplicates("conversation_id").person_label).to_string())
print("\nsample rows:\n", df.head(12).to_string())
