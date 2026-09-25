"""
Title: Exploratory Data Analysis on Framingham Heart Study
Author: Krish
Student ID: [Your Student ID]
Dataset Source: Framingham Heart Study (Provided CSV)
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

# Load the dataset
file_path = "framingham.csv"
df = pd.read_csv(file_path)

# Display dataset information
print("Dataset Information:")
df.info()

# Basic statistics of the dataset
print("\nSummary Statistics:")
print(df.describe())

# Checking for missing values
missing_values = df.isnull().sum()
print("\nMissing Values per Column:")
print(missing_values[missing_values > 0])

# Handling missing values (imputing with median)
df.fillna(df.median(), inplace=True)

# Checking class distribution for target variable
print("\nTarget Variable Distribution:")
print(df["TenYearCHD"].value_counts(normalize=True))

# Visualizing missing data
plt.figure(figsize=(10, 6))
sns.heatmap(df.isnull(), cbar=False, cmap="viridis")
plt.title("Missing Data Heatmap")
plt.show()

# Correlation Heatmap
plt.figure(figsize=(12, 8))
sns.heatmap(df.corr(), annot=True, cmap="coolwarm", fmt=".2f")
plt.title("Feature Correlation Heatmap")
plt.show()

# Histogram of Age
plt.figure(figsize=(8, 5))
sns.histplot(df["age"], bins=20, kde=True)
plt.title("Age Distribution")
plt.xlabel("Age")
plt.ylabel("Frequency")
plt.show()

# Boxplot of Cholesterol Levels
plt.figure(figsize=(8, 5))
sns.boxplot(x=df["totChol"])
plt.title("Total Cholesterol Levels")
plt.xlabel("Total Cholesterol")
plt.show()

# Save processed dataset
df.to_csv("framingham_cleaned.csv", index=False)
print("\nCleaned dataset saved as 'framingham_cleaned.csv'.")
