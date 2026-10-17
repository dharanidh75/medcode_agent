import csv
import faiss
import pickle
import numpy as np
from sentence_transformers import SentenceTransformer
from rank_bm25 import BM25Okapi
import os
import argparse
import json

MODEL_NAME = "abhinand/MedEmbed-large-v0.1"

def parse_diagnoses(filepath):
    codes = []
    descriptions = []
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter=";")
        for row in reader:
            if len(row) >= 9 and row[1] == "T":
                codes.append(row[5])
                descriptions.append(row[8])
    return codes, descriptions

def parse_procedures(filepath):
    codes = []
    descriptions = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            if len(line) > 8:
                codes.append(line[0:7].strip())
                descriptions.append(line[8:].strip())
    return codes, descriptions

def parse_medications(filepath):
    codes = []
    descriptions = []
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
        concepts = data.get("minConceptGroup", {}).get("minConcept", [])
        for concept in concepts:
            codes.append(concept.get("rxcui", ""))
            descriptions.append(concept.get("name", ""))
    return codes, descriptions

def main():
    parser = argparse.ArgumentParser(description="Index medical datasets for FAISS and BM25")
    parser.add_argument("--input", required=True, help="Path to the dataset file")
    parser.add_argument("--domain", required=True, choices=["diagnoses", "procedures", "medications"], help="The domain of the dataset")
    args = parser.parse_args()
    
    out_dir = os.path.join("data", args.domain)
    os.makedirs(out_dir, exist_ok=True)
    
    print(f"Loading {args.domain} dataset from {args.input}...")
    
    if args.domain == "diagnoses":
        codes, descriptions = parse_diagnoses(args.input)
    elif args.domain == "procedures":
        codes, descriptions = parse_procedures(args.input)
    elif args.domain == "medications":
        codes, descriptions = parse_medications(args.input)
        
    print(f"Found {len(codes)} {args.domain} records.")
    if len(codes) == 0:
        print("Error: No codes found. Check the file format.")
        return
        
    print(f"Loading embedding model: {MODEL_NAME}...")
    model = SentenceTransformer(MODEL_NAME)
    
    print("Generating dense embeddings and building FAISS index in chunks...")
    # Determine dimension from a dummy encode
    dummy_emb = model.encode(["test"], convert_to_numpy=True)
    dimension = dummy_emb.shape[1]
    faiss_index = faiss.IndexFlatIP(dimension)
    
    CHUNK_SIZE = 5000
    for i in range(0, len(descriptions), CHUNK_SIZE):
        chunk = descriptions[i:i + CHUNK_SIZE]
        print(f"Processing chunk {i//CHUNK_SIZE + 1} / {(len(descriptions) + CHUNK_SIZE - 1)//CHUNK_SIZE}...")
        # Note: chunk_embeddings is explicitly reassigned each loop, so we don't accumulate them in memory
        chunk_embeddings = model.encode(chunk, show_progress_bar=True, convert_to_numpy=True, batch_size=64)
        faiss.normalize_L2(chunk_embeddings)
        faiss_index.add(chunk_embeddings)
    
    faiss_path = os.path.join(out_dir, "faiss_index.bin")
    faiss.write_index(faiss_index, faiss_path)
    print(f"FAISS index saved to {faiss_path}")
    
    print("Building BM25 index...")
    tokenized_corpus = [desc.lower().split(" ") for desc in descriptions]
    bm25 = BM25Okapi(tokenized_corpus)
    
    metadata = {
        "codes": codes,
        "descriptions": descriptions,
        "bm25": bm25
    }
    
    metadata_path = os.path.join(out_dir, "metadata.pkl")
    with open(metadata_path, "wb") as f:
        pickle.dump(metadata, f)
    print(f"Metadata and BM25 index saved to {metadata_path}")
    print(f"Indexing complete for {args.domain}.")

if __name__ == "__main__":
    main()
