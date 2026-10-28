"""Load outside data into the common schema.

Two kinds of external data are supported:
1. CONVERSATIONS (chat logs with sender + timestamp) -> behaviour-model training/validation.
2. LABELLED MESSAGES (text + label, e.g. HASOC/TRAC/Jigsaw) -> text-model training.

    python external.py inspect path/to/file.csv
    python external.py messages path/to/file.csv --text tweet --label task_2 --map '{"HOF":"insult","NOT":"other"}'
    python external.py conversations path/to/file.csv --conv chat_id --sender from --user-name "Me" \
        --time date --text message --label person_label
    python external.py handwritten data/handwritten
"""
import argparse
import glob
import json
import os

import pandas as pd


def read_any(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in (".csv", ".tsv"):
        return pd.read_csv(path, sep="\t" if ext == ".tsv" else ",", on_bad_lines="skip")
    if ext in (".json", ".jsonl"):
        try:
            return pd.read_json(path, lines=ext == ".jsonl")
        except ValueError:
            return pd.json_normalize(json.load(open(path, encoding="utf-8")))
    if ext == ".parquet":
        return pd.read_parquet(path)
    if ext in (".xlsx", ".xls"):
        return pd.read_excel(path)
    raise ValueError(f"unsupported file type: {ext}")


def inspect(path):
    df = read_any(path)
    print(f"{path}: {len(df)} rows, columns: {list(df.columns)}")
    print(df.head(5).to_string())
    for c in df.columns:
        if df[c].dtype == object and df[c].nunique() < 30:
            print(f"\n{c} values:\n{df[c].value_counts().head(15).to_string()}")
    return df


def labelled_messages(path, text_col, label_col, label_map=None):
    df = read_any(path)
    out = pd.DataFrame({"text": df[text_col].astype(str), "msg_label": df[label_col].astype(str)})
    if label_map:
        out["msg_label"] = out["msg_label"].map(label_map)
    return out.dropna()


def conversations(path, conv_col, sender_col, user_name, time_col, text_col, label_col=None,
                  app="wa", relationship="stranger"):
    df = read_any(path)
    out = pd.DataFrame({
        "conversation_id": df[conv_col].astype(str),
        "person_id": df[conv_col].astype(str),
        "account_id": df[conv_col].astype(str) + "_" + df[sender_col].astype(str),
        "app": app,
        "timestamp": pd.to_datetime(df[time_col], errors="coerce"),
        "is_user": df[sender_col].astype(str) == str(user_name),
        "text": df[text_col].astype(str),
        "reply_label": None,
        "person_label": df[label_col].astype(str) if label_col else None,
    })
    out.loc[out.is_user, "account_id"] = "user"
    out = out.dropna(subset=["timestamp"]).sort_values(["conversation_id", "timestamp"])
    out["msg_id"] = out.groupby("conversation_id").cumcount()
    for col, val in [("user_side_available", True), ("relationship", relationship),
                     ("relationship_age_days", float("nan")), ("is_group", False), ("source", "external"),
                     ("variant", "external"), ("hard_case", False)]:
        out[col] = val
    return out


def handwritten(folder):
    """data/handwritten/*.json -> schema. Each file: one conversation or a list of them:
    {"conversation_id", "person_label", "relationship", "relationship_age_days", "is_group", "hard_case",
     "messages": [{"timestamp", "is_user", "text", "app", "account_id", "msg_label"?, "reply_label"?}]}"""
    rows = []
    for fp in sorted(glob.glob(os.path.join(folder, "*.json"))):
        data = json.load(open(fp, encoding="utf-8"))
        for conv in data if isinstance(data, list) else [data]:
            for i, m in enumerate(conv["messages"]):
                rows.append(dict(
                    conversation_id=conv["conversation_id"], person_id=conv["conversation_id"],
                    account_id=m.get("account_id", "user" if m["is_user"] else "a0"), app=m.get("app", "wa"),
                    msg_id=i, timestamp=pd.to_datetime(m["timestamp"]), is_user=bool(m["is_user"]),
                    text=m.get("text"), msg_label=m.get("msg_label"), reply_label=m.get("reply_label"),
                    user_side_available=True, person_label=conv["person_label"],
                    relationship=conv.get("relationship", "stranger"),
                    relationship_age_days=float(conv.get("relationship_age_days", 0)),
                    is_group=bool(conv.get("is_group", False)), hard_case=bool(conv.get("hard_case", False)),
                    variant="handwritten", source="handwritten"))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["inspect", "messages", "conversations", "handwritten"])
    ap.add_argument("path")
    ap.add_argument("--text"); ap.add_argument("--label"); ap.add_argument("--map")
    ap.add_argument("--conv"); ap.add_argument("--sender"); ap.add_argument("--user-name")
    ap.add_argument("--time"); ap.add_argument("--out", default="data/external")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    if a.mode == "inspect":
        inspect(a.path)
    elif a.mode == "messages":
        df = labelled_messages(a.path, a.text, a.label, json.loads(a.map) if a.map else None)
        df.to_parquet(f"{a.out}/messages.parquet", index=False)
        print(df.msg_label.value_counts().to_string())
    elif a.mode == "conversations":
        df = conversations(a.path, a.conv, a.sender, a.user_name, a.time, a.text, a.label)
        df.to_parquet(f"{a.out}/conversations.parquet", index=False)
        print(f"{df.conversation_id.nunique()} conversations, {len(df)} messages")
    else:
        df = handwritten(a.path)
        df.to_parquet(f"{a.out}/handwritten.parquet", index=False)
        print(f"{df.conversation_id.nunique()} conversations")
