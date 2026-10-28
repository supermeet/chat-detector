"""Map the team-provided dataset (safesphere_behavior_dataset.zip) onto the pipeline schema.

The provided parquet already follows the common schema; this adds the columns the pipeline
expects and derives the hard-case flag from its `scenario` column.

    python prepare_provided.py --src data/provided/synthetic --out data/prepared
"""
import argparse
import os

import pandas as pd

# scenario values in the provided data that are deliberately tricky
HARD_NEGATIVES = {"welcome_clingy", "long_gaps", "one_no", "worried_parent", "swearing_friend"}
HARD_POSITIVES = {"polite_stalker", "polite_fear_reply"}


def prepare(df):
    df = df.copy()
    df["variant"] = df["scenario"].fillna("standard")
    df["hard_case"] = df["variant"].isin(HARD_NEGATIVES | HARD_POSITIVES)
    has_user = df.groupby("person_id")["is_user"].transform("any")
    df["user_side_available"] = has_user
    df["is_group"] = False   # not provided; group behaviour shows up through accounts_count
    if "minor_involved" not in df:
        df["minor_involved"] = False
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="data/provided/synthetic")
    ap.add_argument("--out", default="data/prepared")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    for split in ("train", "test"):
        df = prepare(pd.read_parquet(f"{a.src}/{split}.parquet"))
        df.to_parquet(f"{a.out}/{split}.parquet", index=False)
        conv = df.drop_duplicates("person_id")
        print(f"{split}: {len(conv)} persons, {len(df)} messages, hard cases {int(conv.hard_case.sum())}")


if __name__ == "__main__":
    main()
