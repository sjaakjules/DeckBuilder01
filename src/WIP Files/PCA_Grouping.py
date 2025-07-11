import json
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.compose import ColumnTransformer
import matplotlib.pyplot as plt
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler, FunctionTransformer
from scipy.sparse import issparse
from tqdm import tqdm
import numpy as np


class PCAGrouping:
    def __init__(self, json_path: str):
        with open(json_path, "r", encoding="utf-8") as f:
            self.cards = json.load(f)
        self.data = []
        self.X_pca = None

        # --- Extract guardian features ---
        print("Processing cards for PCA analysis...")
        for card in tqdm(self.cards, desc="Processing cards", unit="card"):
            g = card.get("guardian", {})
            self.data.append({
                "name": card.get("name"),
                "type": g.get("type"),
                "rarity": g.get("rarity"),
                "category": g.get("category"),
                "rulesText": g.get("rulesText") or "",
                "cost": g.get("cost"),
                "attack": g.get("attack"),
                "defense": g.get("defense"),
                "life": g.get("life"),
                "air": int(bool(g.get("airThreshold", 0))),
                "earth": int(bool(g.get("earthThreshold", 0))),
                "fire": int(bool(g.get("fireThreshold", 0))),
                "water": int(bool(g.get("waterThreshold", 0))),
                "element_count": sum([
                    int(bool(g.get("airThreshold", 0))),
                    int(bool(g.get("earthThreshold", 0))),
                    int(bool(g.get("fireThreshold", 0))),
                    int(bool(g.get("waterThreshold", 0))),
                ])
            })

        self.df = pd.DataFrame(self.data)

    def run_pca(self):
        text_features = ["rulesText"]
        type_features = ["type"]
        categorical_features = ["rarity", "category"]
        threshold_features = ["air", "earth", "fire", "water"]
        element_features = ["element_count"]
        other_numeric_features = ["cost", "attack", "defense", "life"]
        
        # Pipelines
        text_pipeline = Pipeline([
            ("flatten", FunctionTransformer(lambda x: x.values.ravel(), validate=False)),
            ("tfidf", TfidfVectorizer(max_features=5)),
            ("weight", FunctionTransformer(lambda x: x.multiply(1.0) if issparse(x) else x * 0.5))
        ])

        categorical_pipeline = Pipeline([
            ("ohe", OneHotEncoder(handle_unknown='ignore')),
            ("weight", FunctionTransformer(lambda x: x.multiply(1.0) if issparse(x) else x * 0.5))
        ])

        type_pipeline = Pipeline([
            ("ohe", OneHotEncoder(handle_unknown='ignore')),
            ("weight", FunctionTransformer(lambda x: x.multiply(1.2) if issparse(x) else x * 0.5))
        ])

        threshold_pipeline = Pipeline([
            ("imputer", SimpleImputer(strategy="constant", fill_value=0)),
            ("scale", StandardScaler()),
            ("weight", FunctionTransformer(lambda x: x.multiply(1.5) if issparse(x) else x * 2.0))
        ])

        element_pipeline = Pipeline([
            ("imputer", SimpleImputer(strategy="constant", fill_value=0)),
            ("scale", StandardScaler()),
            ("weight", FunctionTransformer(lambda x: x.multiply(3.0) if issparse(x) else x * 0.5))
        ])

        other_numeric_pipeline = Pipeline([
            ("imputer", SimpleImputer(strategy="constant", fill_value=0)),
            ("scale", StandardScaler()),
            ("weight", FunctionTransformer(lambda x: x.multiply(0.8) if issparse(x) else x * 0.5))
        ])

        # Combine them
        preprocessor = ColumnTransformer(transformers=[
            ("text", text_pipeline, text_features),
            ("cat", categorical_pipeline, categorical_features),
            ("type", type_pipeline, type_features),
            ("element", element_pipeline, element_features),
            ("thresholds", threshold_pipeline, threshold_features),
            ("numeric", other_numeric_pipeline, other_numeric_features)
        ])
        
        print("Column shapes:")
        for name, transformer, cols in preprocessor.transformers:
            if hasattr(transformer, "fit_transform"):
                Xt = transformer.fit_transform(self.df[cols])
                print(f"{name}: {Xt.shape}")
        
        self.df.fillna(0, inplace=True)
        
        # --- Apply preprocessing ---
        print("Applying preprocessing...")
        X = preprocessor.fit_transform(self.df)
        X_dense = X.toarray() if issparse(X) else X

        # --- PCA ---
        print("Running PCA analysis...")
        pca = PCA(n_components=2)
        self.X_pca = pca.fit_transform(X_dense)
        print(f"PCA complete! Reduced {X_dense.shape[1]} features to 2 dimensions.")
        
        return self.X_pca
    
    def export_dataframe(self, filename="card_data_export.csv"):
        self.df.to_csv(filename, index=False)
        print(f"✅ DataFrame exported to {filename}")
        
    def plot_pca(self):
        # Create result DataFrame
        pca_df = pd.DataFrame(self.X_pca, columns=["PC1", "PC2"])
        pca_df["name"] = self.df["name"]

        # Add element presence
        pca_df["air"] = self.df["air"]
        pca_df["earth"] = self.df["earth"]
        pca_df["fire"] = self.df["fire"]
        pca_df["water"] = self.df["water"]

        def assign_color(row):
            elements = {
                "air": row["air"],
                "earth": row["earth"],
                "fire": row["fire"],
                "water": row["water"]
            }
            active = [k for k, v in elements.items() if v == 1]

            if len(active) == 0:
                return (0, 0, 0)  # Black
            elif len(active) > 1:
                return (0.5, 0, 0.5)  # Purple (RGB)
            else:
                return {
                    "air": (0.53, 0.81, 0.98),     # Light Blue
                    "earth": (0.59, 0.29, 0.0),    # Brown
                    "fire": (1.0, 0.0, 0.0),       # Red
                    "water": (0.0, 0.0, 1.0),      # Blue
                }[active[0]]

        pca_df["color"] = pca_df.apply(assign_color, axis=1)

        # Plot
        plt.figure(figsize=(10, 6))
        plt.scatter(pca_df["PC1"], pca_df["PC2"], c=pca_df["color"].values, alpha=0.6)
        
        for _, row in pca_df.iterrows():
            plt.text(row["PC1"], row["PC2"], row["name"], fontsize=7, alpha=0.6)

        plt.title("PCA of Sorcery Cards")
        plt.xlabel("Principal Component 1")
        plt.ylabel("Principal Component 2")
        plt.grid(True)
        plt.tight_layout()
        plt.show()

if __name__ == "__main__":
    pca = PCAGrouping("data/CardList.json")
    pca.run_pca()
    pca.export_dataframe('card_data_pca.csv')
    pca.plot_pca()